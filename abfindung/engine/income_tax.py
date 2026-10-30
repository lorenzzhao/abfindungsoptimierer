# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Income tax per calendar year and tax unit (joint assessment = one unit).

Order:
 1. income per person: wages by pay period (R_LaufenderArbeitslohn), minus Werbungskosten
    (at least est_arbeitnehmer_pauschbetrag); rental income incl. measures (R_Erhaltung);
    severance as extraordinary income in the year of receipt (R_Entschaedigung, R_Zufluss)
 2. total income with loss offset (R_Verlustausgleich)
 3. special expenses: KV/PV + retirement provisions incl. Basisrente (R_Basisrente),
    childcare, donations, lump sum
 4. children: Günstigerprüfung (R_Guenstigerpruefung)
 5./6. tariff with Fünftelregelung and Progressionsvorbehalt (R_Fuenftel_Progressionsvorbehalt),
    only if Zusammenballung holds (R_Zusammenballung)
 7. Soli (R_Soli), church tax
 8. capital income separately (R_Abgeltung)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..dates import fmt_eur, fmt_pct
from .fifth_rule import est_fuenftel, est_regulaer
from .payroll import kist_rate, soli_freigrenze, soli_on
from .settings import gestaltungen
from .tariff import get_tariff

RV_RATE_IDS = ("rv_beitragssatz_gesamt", "rv_beitragssatz")  # current name first, older name accepted


# -- property purchase (R_Erhaltung, AfA, Disagio) ---------------------------------------

@dataclass
class PropertyYear:
    einkuenfte: float = 0.0
    cash_cost: float = 0.0
    equity: float = 0.0
    steps: list[str] = field(default_factory=list)
    warnings: list = field(default_factory=list)


AFA_PARAM = {"standard": "verm_afa_satz_standard", "ab2023": "verm_afa_satz_ab2023",
             "vor1925": "verm_afa_satz_vor1925", "degressiv": "verm_afa_degressiv_satz"}


def property_year(s, year: int, tb) -> PropertyYear:
    """Sum over all property purchases (entries of kind "kauf" with the transfer in or before the year)."""
    out = PropertyYear()
    for _, g in gestaltungen(s, "kauf"):
        one = property_one(g, year, tb)
        out.einkuenfte += one.einkuenfte
        out.cash_cost += one.cash_cost
        out.equity += one.equity
        out.steps += one.steps
        out.warnings += one.warnings
    return out


def property_one(m, year: int, tb) -> PropertyYear:
    """One purchase ``m`` (Gestaltung of kind "kauf"; jahr/monat = transfer of possession)."""
    out = PropertyYear()
    if year < m.jahr or m.kaufpreis <= 0:
        return out
    tb.rule("R_Erhaltung")
    months = 13 - m.monat if year == m.jahr else 12
    nk = m.kaufpreis * m.nebenkosten_anteil
    ak_gebaeude = (m.kaufpreis + nk) * m.gebaeudeanteil
    grenze = tb.p("verm_anschaffungsnah_grenze")
    jahre_an = int(tb.p("verm_anschaffungsnah_jahre"))
    erh_deductible = 0.0
    basis = ak_gebaeude
    if m.kauf_erhaltung > 0:
        if m.kauf_erhaltung > grenze * ak_gebaeude:
            basis += m.kauf_erhaltung
            out.warnings.append((f"Instandsetzung am gekauften Objekt ({fmt_eur(m.kauf_erhaltung)}) übersteigt "
                                 f"{fmt_pct(grenze, 0)} der Gebäude-AK innerhalb von {jahre_an} Jahren → anschaffungsnahe "
                                 f"Herstellungskosten, nur über AfA.", ["R_Erhaltung"]))
        elif year == m.jahr:
            erh_deductible = m.kauf_erhaltung
    satz = tb.p(AFA_PARAM.get(m.afa_art, "verm_afa_satz_standard"))
    if m.afa_art == "degressiv":
        rest = basis
        afa = 0.0
        for yy in range(m.jahr, year + 1):
            mm = 13 - m.monat if yy == m.jahr else 12
            afa = rest * satz * mm / 12
            rest -= afa
    else:
        afa = basis * satz * months / 12
    zinsen = m.darlehen * m.zins * months / 12
    miete = m.miete_jahr * months / 12
    bew = m.bewirtschaftung_jahr * months / 12
    disagio = m.darlehen * m.disagio_anteil
    dmax = tb.p("verm_disagio_max_anteil")
    dmin = int(tb.p("verm_disagio_min_zinsbindung_jahre"))
    if m.disagio_anteil <= dmax and m.zinsbindung_jahre >= dmin:
        dis_ded = disagio if year == m.jahr else 0.0
        dis_txt = "sofort abziehbar (marktüblich)"
    else:
        n = max(1, m.zinsbindung_jahre)
        dis_ded = disagio / n if m.jahr <= year < m.jahr + n else 0.0
        dis_txt = f"nicht marktüblich → verteilt auf {n} Jahre Zinsbindung"
        if year == m.jahr and disagio > 0:
            out.warnings.append((f"Disagio {fmt_pct(m.disagio_anteil, 1)} über {fmt_pct(dmax, 0)} oder Zinsbindung "
                                 f"unter {dmin} Jahren – nicht sofort abziehbar.", ["R_Erhaltung"]))
    cost_factor = 1.0
    lo = tb.p("verm_verbilligt_untergrenze")
    hi = tb.p("verm_verbilligt_prognosegrenze")
    if m.ortsuebliche_miete_jahr > 0:
        q = m.miete_jahr / m.ortsuebliche_miete_jahr
        if q < lo:
            cost_factor = q
            out.warnings.append((f"Verbilligte Vermietung ({fmt_pct(q, 0)} der ortsüblichen Miete) – Werbungskosten nur "
                                 f"anteilig abziehbar.", ["R_Grenzen_Gestaltung"]))
        elif q < hi:
            out.warnings.append((f"Miete bei {fmt_pct(q, 0)} der ortsüblichen Miete – Totalüberschussprognose nötig.",
                                 ["R_Grenzen_Gestaltung"]))
    werbungskosten = (bew + zinsen + afa + dis_ded + erh_deductible) * cost_factor
    out.einkuenfte = miete - werbungskosten
    out.cash_cost = bew + zinsen + erh_deductible + (disagio if year == m.jahr else 0.0) - miete
    if year == m.jahr:
        out.equity = m.kaufpreis + nk - (m.darlehen - disagio)
    out.steps = [
        f"{m.label}: {months} Monate im Jahr {year} (Besitzübergang Monat {m.monat}/{m.jahr})",
        f"Gebäude-AK = (Kaufpreis {fmt_eur(m.kaufpreis)} + Nebenkosten {fmt_eur(nk)}) × {fmt_pct(m.gebaeudeanteil, 0)} = {fmt_eur(ak_gebaeude)}"
        + (f" + anschaffungsnahe HK {fmt_eur(m.kauf_erhaltung)}" if basis > ak_gebaeude else ""),
        f"AfA {m.afa_art} {fmt_pct(satz, 1)}: {fmt_eur(afa)}; Zinsen {fmt_eur(zinsen)}; Bewirtschaftung {fmt_eur(bew)}; "
        f"Disagio {fmt_eur(dis_ded)} ({dis_txt})" + (f"; Erhaltung {fmt_eur(erh_deductible)}" if erh_deductible else ""),
        f"Einkünfte = Miete {fmt_eur(miete)} − Werbungskosten {fmt_eur(werbungskosten)}"
        + (f" (anteilig {fmt_pct(cost_factor, 0)})" if cost_factor < 1 else "") + f" = {fmt_eur(out.einkuenfte)}",
    ]
    return out


# -- tax unit ------------------------------------------------------------------------

@dataclass
class UnitYear:
    key: str
    year: int
    joint: bool
    pids: list
    gde: float = 0.0
    ae: float = 0.0
    sa: float = 0.0
    v_ohne_kfb: float = 0.0
    kfb: float = 0.0
    kindergeld: float = 0.0
    pv: float = 0.0
    fb_gewaehlt: bool = False
    est: float = 0.0
    soli: float = 0.0
    kist: float = 0.0
    kap: float = 0.0
    salary: float = 0.0
    rv_total: float = 0.0
    basisrente_abzug: float = 0.0
    sonstige: float = 0.0  # deduction of other Gestaltungen (persons of the unit)
    av_frei: float = 0.0  # remaining room for Basisrente below the cap
    tariff: object = None
    kist_satz: float = 0.0
    divisor: int = 5
    params: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.est + self.soli + self.kist

    @property
    def v(self) -> float:
        return self.v_ohne_kfb - (self.kfb if self.fb_gewaehlt else 0.0)

    @property
    def zve(self) -> float:
        return self.v + self.ae

    def tax_for(self, extra_deduction: float = 0.0, extra_income: float = 0.0) -> float:
        """Total tax (ESt + Soli + KiSt) with an additional deduction from v (for charts)."""
        v1 = self.v_ohne_kfb - extra_deduction + extra_income
        e1 = est_fuenftel(v1, self.ae, self.pv, self.tariff, self.joint, self.divisor, False).est
        e2 = est_fuenftel(v1 - self.kfb, self.ae, self.pv, self.tariff, self.joint, self.divisor, False).est
        est = e2 + self.kindergeld if (self.kfb > 0 and e2 + self.kindergeld < e1) else e1
        soli = _soli_fast(e2 if self.kfb > 0 else e1, self.joint, self.params)
        return est + soli + (e2 if self.kfb > 0 else e1) * self.kist_satz


def _soli_fast(tax: float, joint: bool, p: dict) -> float:
    fg = p["soli_fg"]
    if tax <= fg:
        return 0.0
    return min(p["soli_satz"] * tax, p["soli_mild"] * (tax - fg))


def rv_contributions(ps, tl, year: int, rv_satz: float, rv_bbg: float) -> float:
    """Statutory pension contributions (employee + employer) of a person in a year."""
    if not ps.rv_pflichtig:
        return 0.0
    return sum(min(a.gross_old + a.gross_new, rv_bbg) * rv_satz for (yy, _), a in tl.months.items() if yy == year)


def basisrente_for(s, year: int) -> float:
    """Basisrente paid in the year (household, all entries)."""
    return sum(g.betrag for _, g in gestaltungen(s, "basisrente", year))


def amount_for(s, typ: str, year: int) -> float:
    return sum(g.betrag for _, g in gestaltungen(s, typ, year))


def children_tax(s, year: int) -> int:
    """Children considered for allowances / child benefit (basic assumption: under 18)."""
    return sum(1 for gj, kg in s.children if kg and 0 <= year - gj < 18)


def children_under(s, year: int, age: int) -> int:
    return sum(1 for gj, _ in s.children if 0 <= year - gj < age)


def _per_mode(src, joint: bool, joint_id: str, single_id: str, year: int) -> float:
    """Joint value, or the single-assessment parameter (fallback: half the joint value)."""
    if joint:
        return src.p(joint_id, year)
    if src.legal.has(single_id):
        return src.p(single_id, year)
    return src.p(joint_id, year) * 0.5


def compute_unit_year(key: str, members: list, year: int, s, tracer, rs, ctx, joint: bool = True,
                      share: float = 1.0, basis: float | None = None, sa_override: float | None = None) -> UnitYear:
    """Tax of one assessment unit (R_Einzelveranlagung for single units).

    ``members`` = list of (index, PersonSettings); ``share`` = part of the household measures
    (Erhaltung, property, donations, childcare) borne by this unit; ``basis`` = Basisrente
    allocated to the unit; ``sa_override`` = special expenses split half and half (§ 26a Abs. 2 EStG).
    """
    u = UnitYear(key, year, joint, [ps.id for _, ps in members])
    suf = f"{key}{year}"
    grp = f"Steuer {year}" + (f" – {members[0][1].label}" if key else "")
    u.tariff = get_tariff(tracer.legal, year, s.options.tarif_index)
    u.divisor = int(tracer.p("est_fuenftel_divisor"))
    u.params = {"soli_fg": soli_freigrenze(joint, year, tracer), "soli_satz": tracer.p("soli_satz"),
                "soli_mild": tracer.p("soli_milderungssatz")}

    # 1. income ------------------------------------------------------------------
    tb = tracer.new(f"einkuenfte_{suf}", f"Gesamtbetrag der Einkünfte {year}", "EUR", grp)
    tb.rule("R_LaufenderArbeitslohn", "R_Zufluss", "R_Entschaedigung", "R_Verlustausgleich")
    pausch = tb.p("est_arbeitnehmer_pauschbetrag", year)
    gde = 0.0
    ae_priv = 0.0
    ae_children = []
    for idx, ps in members:
        tl = ctx.timelines[ps.id]
        g_old, g_new = tl.gross_in_year(year)
        bonus = ps.bonus if ps.bonus_year == year else 0.0
        salary = g_old + g_new + bonus
        u.salary += salary
        ae_gross = ctx.ae_gross[ps.id].get(year, 0.0)
        ae = max(0.0, ae_gross)
        wk = max(ps.werbungskosten, pausch)
        if wk > pausch:
            nsa = salary - wk
            wk_ae = 0.0
        else:
            used = min(wk, salary)
            nsa = salary - used
            wk_ae = min(wk - used, ae) if (salary + ae) > 0 else 0.0
        ae -= wk_ae
        rent, ry = ps.rent_for(year)
        priv = ctx.privileged(ps.id, year)
        if priv:
            ae_priv += ae
        lab = ps.label
        if salary > 0 or ae > 0 or rent:
            tb.step(f"{lab}: Arbeitslohn {fmt_eur(salary)} (bisheriger AG {fmt_eur(g_old)}"
                    + (f", neue Beschäftigung {fmt_eur(g_new)}" if g_new else "")
                    + (f", Bonus {fmt_eur(bonus)}" if bonus else "")
                    + f") − Werbungskosten {fmt_eur(min(wk, salary) if wk <= pausch else wk)} = {fmt_eur(nsa)}")
            if ae_gross:
                tb.step(f"{lab}: Abfindung {fmt_eur(ae_gross)}"
                        + (f" − restlicher Pauschbetrag {fmt_eur(wk_ae)}" if wk_ae else "")
                        + f" = {fmt_eur(ae)} ({'außerordentlich, § 34' if priv else 'regulär besteuert'})")
                ae_children.append(f"zusammenballung_{ps.id}")
            tb.step(f"{lab}: Vermietung {fmt_eur(rent)}" + (f" (fortgeschrieben aus {ry})" if ry and ry != year else ""))
        if ry and ry != year:
            tb.flag("fortgeschrieben")
        tb.s(f"persons.{idx}.werbungskosten", f"Werbungskosten {lab}")
        tb.s(f"persons.{idx}.salary_mode", f"Gehaltseingabe {lab} (jahr = ganzjährig, real = tatsächlich gezahlt)")
        gde += nsa + rent + ae
    # measures (household) -> rental income
    for gid, g in gestaltungen(s, "erhaltung", year):
        if not g.betrag:
            continue
        tb.s(f"measures.items.{gid}.betrag", g.label)
        gde -= g.betrag * share
        tb.step(f"{g.label}: −{fmt_eur(g.betrag * share)} (sofort abziehbar, R_Erhaltung)")
        tb.rule("R_Erhaltung")
    prop = property_year(s, year, tb)
    if prop.steps:
        gde += prop.einkuenfte * share
        for st in prop.steps:
            tb.step(st)
    ctx.warnings.extend(prop.warnings)
    tb.step(f"Gesamtbetrag der Einkünfte (mit Verlustausgleich) = {fmt_eur(gde)}")
    rs.add(tb.done(gde))
    u.gde = gde
    u.ae = ae_priv

    # 3. special expenses --------------------------------------------------------
    tb = tracer.new(f"vorsorge_{suf}", f"Vorsorgeaufwendungen {year}", "EUR", grp)
    tb.rule("R_Basisrente")
    kv = sum(ctx.kv[ps.id].own_year(year) + ctx.kv[ps.id].an_year(year) for _, ps in members)
    kv_ded = kv
    tb.child(*[f"kv_{ps.id}_{year}" for _, ps in members])
    tb.step(f"KV/PV-Basisabsicherung (eigene Beiträge + Arbeitnehmeranteile): {fmt_eur(kv)}")
    rv_id = tracer.legal.pick(*RV_RATE_IDS)
    if rv_id:
        rv_satz = tb.p(rv_id, year)
    else:
        rv_satz = s.options.rv_satz_annahme
        tb.flag("unsicher")
        if rv_satz > 0:
            tb.s("options.rv_satz_annahme", "RV-Beitragssatz (Annahme, fehlt in rechtlicher XML)")
        ctx.warn("Parameter „rv_beitragssatz_gesamt“ fehlt in den rechtlichen Vorgaben – die Kürzung des Basisrenten-"
                 "Höchstbetrags um RV-Beiträge verwendet den Annahmewert aus den Optionen "
                 f"({fmt_pct(rv_satz, 1)}).", ["R_Basisrente"])
    rv_bbg = tb.p("rv_bbg_monat", year)
    rv_total = sum(rv_contributions(ps, ctx.timelines[ps.id], year, rv_satz, rv_bbg) for _, ps in members)
    u.rv_total = rv_total
    rv_ag = rv_total / 2
    hoechst = tb.p("av_basisrente_hoechstbetrag_je_person", year) * (2 if joint else 1)
    anteil = tb.p("av_basisrente_abzugsanteil", year)
    if basis is None:
        basis = basisrente_for(s, year) * share
    for gid, g in gestaltungen(s, "basisrente", year):
        if basis and g.betrag:
            tb.s(f"measures.items.{gid}.betrag", g.label)
    av = max(0.0, min(rv_total + basis, hoechst) * anteil - rv_ag)
    u.av_frei = max(0.0, hoechst - rv_total - basis)
    u.basisrente_abzug = max(0.0, min(rv_total + basis, hoechst) - rv_total) * anteil if basis else 0.0
    if basis > hoechst - rv_total:
        ctx.warn(f"Basisrente {year} ({fmt_eur(basis)}) übersteigt den verbleibenden Höchstbetrag "
                 f"({fmt_eur(max(0.0, hoechst - rv_total))}).", ["R_Basisrente"])
    tb.step(f"Altersvorsorge: gesetzliche RV (AN + AG) {fmt_eur(rv_total)} + Basisrente {fmt_eur(basis)}, "
            f"höchstens {fmt_eur(hoechst)} ({'× 2 Personen' if joint else 'eine Person'}), × {fmt_pct(anteil, 0)}, "
            f"− steuerfreier AG-Anteil {fmt_eur(rv_ag)} = {fmt_eur(av)}")
    vors = kv_ded + av
    tb.step(f"Vorsorgeaufwendungen gesamt = {fmt_eur(vors)}")
    rs.add(tb.done(vors))

    tb = tracer.new(f"sa_{suf}", f"Sonderausgaben {year}", "EUR", grp)
    tb.child(f"vorsorge_{suf}")
    cost, cy = _for_year(s.childcare, year)
    cost *= share
    n14 = children_under(s, year, 14)
    betr = 0.0
    if cost and n14:
        betr = min(tb.p("kind_betreuung_anteil", year) * cost, tb.p("kind_betreuung_hoechstbetrag", year) * n14)
        tb.step(f"Kinderbetreuung: min({fmt_pct(tracer.p('kind_betreuung_anteil', year), 0)} × {fmt_eur(cost)}; "
                f"{fmt_eur(tracer.p('kind_betreuung_hoechstbetrag', year))} × {n14} Kinder unter 14) = {fmt_eur(betr)}")
        if cy and cy != year:
            tb.flag("fortgeschrieben").step(f"Betreuungskosten aus {cy} fortgeschrieben.")
    spende = 0.0
    sp_total = amount_for(s, "spende", year)
    if sp_total:
        spende = min(sp_total * share, tb.p("est_spenden_hoechstanteil") * max(0.0, gde))
        for gid, g in gestaltungen(s, "spende", year):
            tb.s(f"measures.items.{gid}.betrag", g.label)
        tb.step(f"Spenden: {fmt_eur(spende)} (höchstens {fmt_pct(tracer.p('est_spenden_hoechstanteil'), 0)} des GdE)")
    sa_p = _per_mode(tb, joint, "est_sonderausgaben_pauschbetrag_zusammen", "est_sonderausgaben_pauschbetrag_einzeln", year)
    other = max(betr + spende, sa_p)
    if betr + spende < sa_p:
        tb.step(f"Sonderausgaben-Pauschbetrag {fmt_eur(sa_p)} statt {fmt_eur(betr + spende)}")
    sa = vors + other
    tb.step(f"Sonderausgaben = Vorsorge {fmt_eur(vors)} + übrige {fmt_eur(other)} = {fmt_eur(sa)}")
    if sa_override is not None:
        tb.rule("R_Einzelveranlagung")
        if tracer.legal.has("est_einzelveranlagung_sonderausgaben_haelftig"):
            tb.p("est_einzelveranlagung_sonderausgaben_haelftig")
        tb.step(f"Einzelveranlagung, Sonderausgaben auf Antrag je zur Hälfte (§ 26a Abs. 2 EStG): {fmt_eur(sa_override)}")
        sa = sa_override
    rs.add(tb.done(sa))
    u.sa = sa

    # other Gestaltungen: deductible share reduces the income of the assigned person -------------
    pids = {ps.id for _, ps in members}
    sonst = [(gid, g) for gid, g in gestaltungen(s, "sonstige", year) if g.person in pids and g.betrag]
    u.sonstige = 0.0
    if sonst:
        tb = tracer.new(f"sonstige_{suf}", f"Sonstige Gestaltungen {year}", "EUR", grp)
        for gid, g in sonst:
            share_d = tb.s(f"measures.items.{gid}.abziehbar", f"Abziehbarer Anteil {g.label}")
            tb.s(f"measures.items.{gid}.betrag", g.label)
            ded = g.betrag * share_d
            u.sonstige += ded
            who = next(ps.label for _, ps in members if ps.id == g.person)
            tb.step(f"{g.label} ({who}): {fmt_eur(g.betrag)} × {fmt_pct(share_d, 0)} abziehbar = {fmt_eur(ded)}")
        tb.step(f"Abzug vom Einkommen gesamt {fmt_eur(u.sonstige)} (eigene Angabe zur Abziehbarkeit, ohne Höchstbetrag)")
        tb.flag("unsicher")
        rs.add(tb.done(u.sonstige))

    # 4.-7. tax ---------------------------------------------------------------------
    u.v_ohne_kfb = gde - u.ae - sa - u.sonstige
    n_k = children_tax(s, year)
    if joint or not tracer.legal.has("kind_freibetrag_saechlich_je_elternteil"):
        kfb_one = tracer.p("kind_freibetrag_gesamt_zusammen", year) * (1 if joint else 0.5)
    else:  # single assessment: allowances per parent (R_Einzelveranlagung)
        kfb_one = (tracer.p("kind_freibetrag_saechlich_je_elternteil", year)
                   + tracer.p("kind_freibetrag_bea_je_elternteil", year))
    u.kfb = kfb_one * n_k
    u.kindergeld = tracer.p("kind_kindergeld_monat", year) * 12 * n_k * (1 if joint else 0.5)
    u.pv = sum(ctx.timelines[ps.id].alg_in_year(year) for _, ps in members)

    claims = [ps for _, ps in members if ps.austritt and ps.alg_aktiv]
    if claims:  # without any ALG claim in the unit there is nothing to show
        tb = tracer.new(f"pv_{suf}", f"Progressionsvorbehalt (ALG) {year}", "EUR", grp)
        tb.rule("R_ALG_Steuer", "R_Progressionsvorbehalt").child(*[f"alg_{ps.id}_{year}" for ps in claims])
        tb.step("Summe ALG des Jahres (steuerfrei, wirkt nur auf den Steuersatz) = " + fmt_eur(u.pv))
        if len(claims) < len(members):
            tb.step("Kein ALG für: " + ", ".join(ps.label for _, ps in members if ps not in claims)
                    + " (nicht beantragt bzw. kein Austritt).")
        rs.add(tb.done(u.pv))

    full = s.options.guenstiger_mode == "voll"
    r1 = est_fuenftel(u.v_ohne_kfb, u.ae, u.pv, u.tariff, joint, u.divisor)
    r2 = est_fuenftel(u.v_ohne_kfb - u.kfb, u.ae, u.pv, u.tariff, joint, u.divisor)
    if full:
        cmp1, cmp2 = r1.est, r2.est
    else:  # compare on the plain tariff only
        cmp1 = u.tariff.st(u.v_ohne_kfb + u.ae, joint)
        cmp2 = u.tariff.st(u.v_ohne_kfb + u.ae - u.kfb, joint)
    u.fb_gewaehlt = u.kfb > 0 and cmp2 + u.kindergeld < cmp1
    chosen = r2 if u.fb_gewaehlt else r1
    u.est = chosen.est + (u.kindergeld if u.fb_gewaehlt else 0.0)
    soli_base = r2.est if u.kfb > 0 else r1.est

    tb = tracer.new(f"v_{suf}", f"Verbleibendes zvE v {year}", "EUR", grp)
    tb.rule("R_Fuenftel_Progressionsvorbehalt", "R_Guenstigerpruefung").child(f"einkuenfte_{suf}", f"sa_{suf}")
    tb.step(f"v = GdE {fmt_eur(gde)} − außerordentliche Einkünfte {fmt_eur(u.ae)} − Sonderausgaben {fmt_eur(sa)}"
            + (f" − Kinderfreibeträge {fmt_eur(u.kfb)}" if u.fb_gewaehlt else "") + f" = {fmt_eur(u.v)}")
    if u.v < 0 and u.pv > 0:
        tb.step("v ist negativ: das ALG wird zuerst mit dem negativen v verrechnet (BFH).")
    rs.add(tb.done(u.v))

    tb = tracer.new(f"zve_{suf}", f"Zu versteuerndes Einkommen {year}", "EUR", grp)
    tb.child(f"v_{suf}", *ae_children)
    tb.step(f"zvE = v {fmt_eur(u.v)} + außerordentliche Einkünfte {fmt_eur(u.ae)} = {fmt_eur(u.zve)}")
    rs.add(tb.done(u.zve))

    tb = tracer.new(f"est_{suf}", f"Einkommensteuer {year}", "EUR", grp)
    tb.rule("R_Fuenftel_Progressionsvorbehalt", "R_Guenstigerpruefung")
    if u.ae:
        tb.rule("R_Fuenftel_Normal" if u.v >= 0 else "R_Fuenftel_Negativ")
    tb.child(f"v_{suf}", f"pv_{suf}", f"zve_{suf}")
    tb.p("est_fuenftel_divisor")
    tb.step(u.tariff.describe() + (" – Splitting" if joint else " – Grundtarif"))
    if u.tariff.fortgeschrieben:
        tb.flag("fortgeschrieben")
        if s.options.tarif_index:
            tb.s("options.tarif_index", "Fortschreibung Tarif (% p. a.)")
    if n_k:
        tb.p("kind_freibetrag_gesamt_zusammen", year)
        tb.p("kind_kindergeld_monat", year)
        tb.step(f"Günstigerprüfung ({n_k} Kinder{'' if full else ', Vergleich nur auf Tarifbasis'}): "
                f"ohne Freibeträge {fmt_eur(cmp1)} vs. mit Freibeträgen {fmt_eur(cmp2)} + Kindergeld {fmt_eur(u.kindergeld)} "
                f"= {fmt_eur(cmp2 + u.kindergeld)} → " + ("Freibeträge günstiger, Kindergeld wird hinzugerechnet"
                                                           if u.fb_gewaehlt else "Kindergeld günstiger"))
    for st in chosen.steps:
        tb.step(st)
    if u.fb_gewaehlt:
        tb.step(f"+ Hinzurechnung Kindergeld {fmt_eur(u.kindergeld)} → festzusetzende ESt {fmt_eur(u.est)}")
    if not s.options.guenstiger_mode == "voll":
        tb.flag("unsicher")
    rs.add(tb.done(u.est))

    tb = tracer.new(f"soli_{suf}", f"Solidaritätszuschlag {year}", "EUR", grp)
    tb.rule("R_Soli").child(f"est_{suf}")
    u.soli = soli_on(soli_base, joint, year, tb)
    fg = soli_freigrenze(joint, year, tracer)
    tb.step(f"Bemessung: ESt mit Kinderfreibeträgen, ohne Kindergeld = {fmt_eur(soli_base)} (soli_bemessung_kinder)")
    tb.step(f"Freigrenze {fmt_eur(fg)}; Soli = " + ("0" if soli_base <= fg else
            f"min({fmt_pct(tracer.p('soli_satz'), 1)} × {fmt_eur(soli_base)}; {fmt_pct(tracer.p('soli_milderungssatz'), 1)} × "
            f"({fmt_eur(soli_base)} − {fmt_eur(fg)})) = {fmt_eur(u.soli, 2)}"))
    rs.add(tb.done(u.soli))

    u.kist_satz = kist_rate(s, tracer)
    u.kist = soli_base * u.kist_satz
    tb = tracer.new(f"kist_{suf}", f"Kirchensteuer {year}", "EUR", grp)
    tb.s("options.church", "Kirchensteuerpflicht")
    if u.kist_satz:
        tb.s("options.bundesland", "Bundesland")
        tb.p("kist_satz_by_bw" if s.options.bundesland.upper() in ("BY", "BW") else "kist_satz_sonst")
        tb.step(f"KiSt = {fmt_pct(u.kist_satz, 0)} × {fmt_eur(soli_base)} = {fmt_eur(u.kist, 2)}")
    else:
        tb.step("Keine Kirchensteuer (nicht kirchensteuerpflichtig).")
    rs.add(tb.done(u.kist))

    tb = tracer.new(f"steuer_{suf}", f"Steuer gesamt {year} (ESt + Soli + KiSt)", "EUR", grp)
    tb.child(f"est_{suf}", f"soli_{suf}", f"kist_{suf}", f"nullgrenze_{suf}")
    tb.step(f"{fmt_eur(u.est)} + {fmt_eur(u.soli, 2)} + {fmt_eur(u.kist, 2)} = {fmt_eur(u.total, 2)}")
    rs.add(tb.done(u.total))

    # Ä7: Nullgrenze for every year
    tb = tracer.new(f"nullgrenze_{suf}", f"Abzug bis zur Nullgrenze {year}", "EUR", grp)
    tb.rule("R_Fuenftel_Progressionsvorbehalt", "R_Basisrente").child(f"v_{suf}", f"pv_{suf}")
    ng = max(0.0, u.v + u.pv)
    if u.pv > 0:
        tb.step(f"Nullgrenze: zusätzlicher Abzug, bei dem übriges zvE + ALG = 0 wird = {fmt_eur(u.v)} + {fmt_eur(u.pv)} "
                f"= {fmt_eur(ng)}")
    else:
        tb.step(f"Nullgrenze: zusätzlicher Abzug, bei dem das übrige zvE = 0 wird (kein ALG) = {fmt_eur(ng)}")
    if not u.ae:
        tb.step("In diesem Jahr gibt es keine Abfindung: ein Abzug wirkt mit dem normalen Grenzsteuersatz.")
    if ng > 0 and u.ae:
        t0 = u.tax_for(0)
        t1 = u.tax_for(min(ng, 1000))
        tb.step(f"Bis dorthin wirkt ein Abzug fast vollständig: die ersten {fmt_eur(min(ng, 1000))} Abzug sparen "
                f"{fmt_eur(t0 - t1)} Steuer. Danach wirkt er nur noch mit dem Grenzsatz auf das Fünftel.")
        if basis:
            tb.step(f"Bereits angesetzte Basisrente {fmt_eur(basis)}; verbleibender Höchstbetrag {fmt_eur(u.av_frei)}.")
    elif u.ae:
        tb.step("Die Nullgrenze ist bereits erreicht; weitere Abzüge wirken nur noch über das Fünftel.")
    tb.step(f"Verbleibender Basisrenten-Höchstbetrag {fmt_eur(u.av_frei)}. Basisrente bindet Vermögen bis zum "
            "Rentenbeginn und wird später voll versteuert (Steuerverschiebung).")
    if u.ae and u.pv <= 0:
        tb.step("Zonen der Grenzbelastung (Diagramm „Steuer & Knick“): unter der Nullgrenze wirkt nur das Fünftel; über 0 "
                "bis ca. 160 %, solange das übrige zvE im Grundfreibetrag liegt (5 × Grenzsatz oben − 4 × Grenzsatz unten).")
    if u.ae and u.pv > 0:
        tb.step("Zonen der Grenzbelastung (Diagramm „Steuer & Knick“): unter der Nullgrenze mit ALG ca. 25–35 %; "
                "zwischen −ALG und 0 ca. 75–100 %; über 0 bis ca. 160 %, solange das übrige zvE im Grundfreibetrag liegt "
                "(5 × Grenzsatz oben − 4 × Grenzsatz unten).")
        tb.step("Die Grenzbelastung von 160 bis 190 % gilt nur für steuerpflichtiges Einkommen oberhalb der Nullgrenze, "
                "nicht für ALG. ALG wirkt nur auf den Steuersatz und wird nach BFH VI R 44/07 zuerst mit einem negativen "
                "übrigen zvE verrechnet.")
    rs.add(tb.done(ng))

    # Ä10: deductions beyond the Nullgrenze only act on the fifth
    erh = amount_for(s, "erhaltung", year) * share
    ded = basis + erh + u.sonstige
    below = -(u.v + u.pv)
    if u.ae and ded > 0 and below > 500:
        over = min(ded, below)
        eff = (u.tax_for(extra_income=over) - u.tax_for(0)) / over
        ctx.warn(f"{year}: Abzüge (Basisrente/Erhaltung/Sonstige) gehen um {fmt_eur(over)} über die Nullgrenze hinaus; dieser Teil "
                 f"spart nur ca. {fmt_pct(eff, 0)} Steuer. Nur sinnvoll mit Vorsorgeabsicht bzw. wenn die Maßnahme ohnehin "
                 f"nötig ist.", ["R_Gestaltungsrisiko", "R_Fuenftel_Progressionsvorbehalt"])

    # Ä9: tax-free base of the Fünftelregelung
    if u.ae:
        gfb = tracer.p("est_grundfreibetrag", year)
        cap = u.divisor * gfb * (2 if joint else 1)
        tb = tracer.new(f"sockel_{suf}", f"Steuerfreier Sockel der Fünftelregelung {year}", "Text", grp)
        tb.rule("R_Fuenftel_Negativ", "R_Fuenftel_Progressionsvorbehalt").child(f"zve_{suf}", f"nullgrenze_{suf}")
        tb.p("est_grundfreibetrag", year)
        tb.step(f"Ist das übrige zvE ≤ 0 und kein ALG-Rest vorhanden, gilt ESt = {u.divisor} × St(zvE / {u.divisor}). "
                f"Steuerfrei bleibt dann ein zvE bis {u.divisor} × {'2 × ' if joint else ''}Grundfreibetrag = {fmt_eur(cap)}.")
        if u.v + u.pv <= 0:
            used = min(cap, max(0.0, u.zve))
            tb.step(f"zvE (Abfindung zuzüglich negativem übrigem zvE) {fmt_eur(u.zve)} → genutzt {fmt_eur(used)} von {fmt_eur(cap)}")
            val = f"{fmt_eur(used)} von {fmt_eur(cap)}"
        else:
            tb.step(f"Übriges zvE + ALG = {fmt_eur(u.v + u.pv)} > 0: der Sockel greift nicht.")
            val = f"nicht genutzt (0 € von {fmt_eur(cap)})"
        rs.add(tb.done(val))

    # capital income (R_Abgeltung) ---------------------------------------------------
    kap = sum(ps.capital_for(year)[0] for _, ps in members)
    tb = tracer.new(f"kap_{suf}", f"Abgeltungsteuer Kapitalerträge {year}", "EUR", grp)
    tb.rule("R_Abgeltung")
    sp = _per_mode(tb, joint, "kap_sparer_pauschbetrag_zusammen", "kap_sparer_pauschbetrag_einzeln", year)
    satz = tb.p("kap_abgeltung_satz")
    basis_k = max(0.0, kap - sp)
    st = basis_k * satz
    soli_k = st * tracer.p("soli_satz")
    kist_k = st * u.kist_satz
    u.kap = st + soli_k + kist_k
    tb.step(f"({fmt_eur(kap)} − Sparer-Pauschbetrag {fmt_eur(sp)}) × {fmt_pct(satz, 0)} = {fmt_eur(st, 2)}; "
            f"+ Soli {fmt_eur(soli_k, 2)}" + (f" + KiSt {fmt_eur(kist_k, 2)}" if kist_k else ""))
    tb.step("Nicht im zvE; kein Einfluss auf Fünftelregelung und Progressionsvorbehalt. Nicht Teil des Saldos (konstant).")
    if any(ps.capital_for(year)[1] != year for _, ps in members):
        tb.flag("fortgeschrieben")
    rs.add(tb.done(u.kap))
    return u


def _for_year(d: dict, year: int):
    if not d:
        return 0.0, None
    if year in d:
        return d[year], year
    earlier = [y for y in d if y < year]
    y = max(earlier) if earlier else min(d)
    return d[y], y
