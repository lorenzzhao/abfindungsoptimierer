# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Run one scenario: settings + legal data -> complete, traceable result.

Target value (Saldo) over the horizon:
    Saldo = Σ ALG − Σ (ESt + Soli + KiSt) − Σ own KV/PV contributions − Σ cash cost of measures
            + Σ net wage (optional) − weight × tied-up assets (default weight 0)
Tied-up assets (Basisrente) are not a loss; they are shown separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..dates import fmt_date, fmt_eur, fmt_pct
from .alg import alg_rate
from .derive import derive_person
from .health import KvResult, build_kv
from .income_tax import UnitYear, basisrente_for, compute_unit_year, property_one, rv_contributions
from .trace import ResultSet, Tracer
from .settings import SECTIONS, effective, gestaltungen
from .timeline import alg_traces, build_timeline


@dataclass
class Context:
    timelines: dict = field(default_factory=dict)
    kv: dict = field(default_factory=dict)
    ae_gross: dict = field(default_factory=dict)    # pid -> {year: amount}
    payments: dict = field(default_factory=dict)    # pid -> [(month_idx, amount)]
    priv: dict = field(default_factory=dict)        # (pid, year) -> bool
    derived: dict = field(default_factory=dict)     # settings path -> (value, trace id) for origin "abgeleitet"
    n_units: int = 1
    warnings: list = field(default_factory=list)

    def privileged(self, pid: str, year: int) -> bool:
        return self.priv.get((pid, year), False)

    def warn(self, text: str, rules: list[str]) -> None:
        if (text, rules) not in self.warnings:
            self.warnings.append((text, rules))


@dataclass
class Result:
    settings: object
    rs: ResultSet
    ctx: Context
    units: dict            # (key, year) -> UnitYear
    years: list
    saldo: float
    saldo_by_year: dict
    tax_by_year: dict
    alg_by_year: dict
    kv_by_year: dict
    cost_by_year: dict
    salary_by_year: dict
    gebunden: float
    liquidity: list = field(default_factory=list)
    liq_min: float = 0.0
    liq_min_month: tuple | None = None
    tracer: Tracer | None = None
    extra: dict = field(default_factory=dict)
    raw_settings: object = None

    @property
    def warnings(self):
        return self.ctx.warnings

    def main_unit_year(self) -> UnitYear | None:
        """Unit-year with the largest extraordinary income (severance year)."""
        best = None
        for u in self.units.values():
            if best is None or u.ae > best.ae:
                best = u
        return best


def _payments(ps) -> list[tuple[int, float]]:
    """The severance is paid in one amount (no instalments)."""
    return [(ps.pay_idx, ps.severance)]


def run(s, legal, explain: bool = True, extras: bool = True) -> Result:
    raw = s
    s = effective(raw, legal)  # disabled input areas are neutralised
    tracer = Tracer(legal, s)
    rs = ResultSet()
    ctx = Context()
    ctx.derived = tracer.derived
    _section_notes(raw, ctx)
    o = s.options
    leaving = [ps for ps in s.persons if ps.austritt]
    if o.horizon_auto:
        o.horizon_start = min(ps.end_date.year for ps in leaving) if leaving else s.stand.year
        o.horizon_end = _latest_payment_year(s)
    sim_end = date(max([o.horizon_end] + [ps.meldung.year for ps in leaving if ps.alg_aktiv]) + 3, 12, 31)
    for ps in s.persons:
        if ps.austritt and not ps.alg_aktiv:  # registration after the simulated period: no ALG
            ps.meldung = date(sim_end.year + 1, 1, 1)
            ctx.warn(f"{ps.label}: kein Arbeitslosengeld beantragt – keine Meldung bei der Agentur für Arbeit; nach dem "
                     "Austritt KV über den nachgehenden Anspruch, die Familienversicherung oder freiwillig.", [])
        if not ps.austritt:  # the employment continues beyond the simulated period
            ps.end_date = ps.geplantes_ende = date(sim_end.year + 1, 12, 31)
            ps.meldung = ps.end_date + timedelta(days=1)
            ps.arbeitsuchend_datum = ps.vertragsschluss
            ctx.warn(f"{ps.label}: kein Austritt – die Beschäftigung läuft im ganzen Horizont weiter (Gehalt, "
                     "Arbeitnehmeranteile KV/PV); keine Abfindung, kein ALG.", [])

    for idx, ps in enumerate(s.persons):
        derive_person(ps, idx, s, tracer, rs)

    # severance per person and year --------------------------------------------------------
    for idx, ps in enumerate(s.persons):
        pays = _payments(ps)
        ctx.payments[ps.id] = pays
        by_year: dict[int, float] = {}
        for mi, amount in pays:
            by_year[mi // 12] = by_year.get(mi // 12, 0.0) + amount
        ctx.ae_gross[ps.id] = by_year

    # timelines, ALG, KV ----------------------------------------------------------
    for idx, ps in enumerate(s.persons):
        rate_t, rate_tag = alg_rate(ps, idx, s, tracer)
        rs.add(rate_t)
        tl = build_timeline(ps, idx, s, tracer, rs, rate_tag, sim_end)
        ctx.timelines[ps.id] = tl
        ctx.warnings.extend(tl.warnings)
    _horizon(s, tracer, rs, ctx)
    years = s.years()
    for idx, ps in enumerate(s.persons):
        alg_traces(ctx.timelines[ps.id], ps, s, tracer, rs)
        if not (ps.austritt and ps.alg_aktiv):
            _without_alg(ps, s, tracer, rs)
        _check_window(ps, ctx)
    for idx, ps in enumerate(s.persons):
        _zusammenballung(ps, idx, s, tracer, rs, ctx)
    for idx, ps in enumerate(s.persons):
        if not s.active("kv") or not ps.kv_aktiv:
            ctx.kv[ps.id] = KvResult()
            if s.active("kv"):
                ctx.warn(f"{ps.label}: Krankenversicherung nicht berücksichtigt – keine eigenen KV/PV-Beiträge und keine "
                         "Arbeitnehmeranteile, daher auch keine KV/PV-Vorsorgeaufwendungen.", [])
            continue
        ctx.kv[ps.id] = build_kv(ps, idx, s, tracer, rs, ctx.timelines[ps.id], ctx.payments[ps.id],
                                 dict(ctx.ae_gross[ps.id]))

    # income tax per year: joint or single assessment (R_Einzelveranlagung) ---------------
    unit_years: dict = {}
    year_keys: dict = {}
    for y in years:
        for u in _tax_year(y, s, tracer, rs, ctx):
            unit_years[(u.key, y)] = u
            year_keys.setdefault(y, []).append(u.key)
    _measure_warnings(s, ctx, tracer)

    # saldo -------------------------------------------------------------------------
    o = s.options
    saldo_by_year, tax_by_year, alg_by_year, kv_by_year, cost_by_year, sal_by_year = {}, {}, {}, {}, {}, {}
    gegenwert_by_year = {}
    for y in years:
        tax = sum(unit_years[(k, y)].total for k in year_keys[y])
        alg = sum(ctx.timelines[ps.id].alg_in_year(y) for ps in s.persons)
        kv = sum(ctx.kv[ps.id].own_year(y) for ps in s.persons)
        cost = gw = 0.0
        tbc = tracer.new(f"aufwand_{y}", f"Aufwand der Gestaltungen {y} (ohne Gegenwert)", "EUR", "Saldo")
        tbc.rule("R_Grenzen_Gestaltung")

        def item(gid: str, label: str, amount: float) -> None:
            nonlocal cost, gw
            share = tbc.s(f"measures.items.{gid}.gegenwert", f"Gegenwert {label}")
            cost += (1 - share) * amount
            gw += share * amount
            tbc.step(f"{label} {fmt_eur(amount)}, Gegenwert {fmt_pct(share, 0)} → Aufwand {fmt_eur((1 - share) * amount)}")

        for gid, g in gestaltungen(s, year=y):
            if g.typ != "kauf" and g.betrag:
                item(gid, g.label, g.betrag)
        for gid, g in gestaltungen(s, "kauf"):
            one = property_one(g, y, tracer.new("_tmp", "", "EUR"))
            if y >= g.jahr and g.kaufpreis > 0:
                item(gid, f"{g.label}, laufende Netto-Kosten (Zinsen + Bewirtschaftung + Disagio − Miete)", one.cash_cost)
                if one.equity:
                    tbc.step(f"Eigenkapital {fmt_eur(one.equity)}, Kaufpreis und Tilgung sind Vermögensumschichtung, "
                             "kein Aufwand.")
        if not tbc.t.steps:
            tbc.step("Keine Gestaltungen in diesem Jahr.")
        else:
            tbc.step("Gegenwert = Anteil, der als Vermögen oder persönlicher Wert erhalten bleibt (Annahme je Gestaltung); "
                     "die Steuerwirkung zählt immer voll.")
        rs.add(tbc.done(cost))

        tbs = tracer.new(f"gehalt_netto_{y}", f"Gehalt im Saldo {y} (abzgl. Sozialabgaben, ohne Gegenwert)", "EUR", "Saldo")
        net = 0.0
        rv_bbg = tracer.p("rv_bbg_monat", y)
        for ps in s.persons:
            tl = ctx.timelines[ps.id]
            for (yy, mm), agg in tl.months.items():
                if yy == y:
                    g = agg.gross_old + agg.gross_new
                    net += g - o.sozialabgaben_anteil * min(g, rv_bbg)
            if ps.bonus and ps.bonus_year == y:
                net += ps.bonus * (1 - o.sozialabgaben_anteil)
        tbs.s("options.sozialabgaben_anteil", "Sozialabgabenanteil am Gehalt")
        share = tbs.s("options.gegenwert_arbeitszeit", "Gegenwert der Arbeitszeit")
        sal = (1 - share) * net
        tbs.step(f"Bruttogehalt (bisheriger AG, neue Beschäftigung) abzüglich Sozialabgaben "
                 f"{fmt_pct(o.sozialabgaben_anteil, 0)} bis zur BBG = {fmt_eur(net)}")
        tbs.step(f"Gegenwert der Arbeitszeit {fmt_pct(share, 0)} → im Saldo {fmt_eur(net)} × {fmt_pct(1 - share, 0)} = "
                 f"{fmt_eur(sal)}")
        tbs.step("Gegenwert = Wert der freien Zeit im Verhältnis zum Nettogehalt (0 % = Freizeit ohne eigenen Wert, "
                 "100 % = Freizeit so viel wert wie das Gehalt). Die Steuer auf das Gehalt steckt immer voll in der ESt.")
        rs.add(tbs.done(sal))

        gegenwert_by_year[y] = gw
        sy = alg - tax - kv - cost + sal
        tb = tracer.new(f"saldo_{y}", f"Saldo {y}", "EUR", "Saldo")
        tb.child(*[f"alg_{ps.id}_{y}" for ps in s.persons], f"steuer_{y}",
                 *[f"kv_{ps.id}_{y}" for ps in s.persons], f"aufwand_{y}", f"gehalt_netto_{y}")
        tb.step(f"ALG {fmt_eur(alg)} − Steuer {fmt_eur(tax)} − eigene KV/PV {fmt_eur(kv)} − Aufwand {fmt_eur(cost)}"
                + f" + Gehalt im Saldo {fmt_eur(sal)}"
                + f" = {fmt_eur(sy)}")
        rs.add(tb.done(sy))
        saldo_by_year[y], tax_by_year[y], alg_by_year[y], kv_by_year[y] = sy, tax, alg, kv
        cost_by_year[y], sal_by_year[y] = cost, sal

    saldo = sum(saldo_by_year.values())
    gebunden = sum(gegenwert_by_year.values())
    tb = tracer.new("gebunden", "Gegenwert der Gestaltungen (nicht im Saldo)", "EUR", "Übersicht")
    tb.child(*[f"aufwand_{y}" for y in years])
    tb.step(" + ".join(f"{y}: {fmt_eur(v)}" for y, v in gegenwert_by_year.items()) + f" = {fmt_eur(gebunden)}")
    tb.step("Vermögen oder persönlicher Wert, der den Gestaltungen gegenübersteht, aber nicht frei verfügbar ist "
            "(z. B. Basisrente bis Rentenbeginn gebunden, spätere Leistungen sind steuerpflichtig).")
    if any(basisrente_for(s, y) for y in years):
        tb.rule("R_Basisrente")
    rs.add(tb.done(gebunden))

    res = Result(s, rs, ctx, unit_years, years, saldo, saldo_by_year, tax_by_year, alg_by_year, kv_by_year,
                 cost_by_year, sal_by_year, gebunden, tracer=tracer, raw_settings=raw)
    if extras:
        from .liquidity import build_liquidity
        from .pension import pension_traces

        build_liquidity(res, s, tracer, rs, ctx)
        pension_traces(res, s, tracer, rs, ctx)

    tb = tracer.new("saldo", "Netto-Saldo über den Horizont", "EUR", "Übersicht")
    tb.child(*[f"saldo_{y}" for y in years], "gebunden")
    tb.step("Saldo = Σ ALG − Σ (ESt + Soli + KiSt) − Σ eigene KV/PV − Σ Aufwand der Gestaltungen ohne Gegenwert"
            + " + Σ Gehalt abzgl. Sozialabgaben ohne Gegenwert der Arbeitszeit")
    tb.step(" + ".join(f"{y}: {fmt_eur(v)}" for y, v in saldo_by_year.items()) + f" = {fmt_eur(saldo)}")
    tb.step(f"Horizont {years[0]}–{years[-1]}. Abfindung brutto und Abgeltungsteuer sind konstant und nicht enthalten.")
    rs.add(tb.done(saldo))
    tb = tracer.new("steuer_gesamt", "Gesamtsteuer über den Horizont", "EUR", "Übersicht")
    tb.child(*[f"steuer_{y}" for y in years])
    total_tax = sum(tax_by_year.values())
    tb.step("Einkommensteuer + Solidaritätszuschlag + Kirchensteuer je Jahr (nach der gewählten bzw. günstigeren "
            "Veranlagung): " + " + ".join(f"{y}: {fmt_eur(v)}" for y, v in tax_by_year.items()) + f" = {fmt_eur(total_tax)}")
    tb.step("Ohne Abgeltungsteuer auf Kapitalerträge (an der Quelle abgegolten, in allen Einstellungen gleich).")
    rs.add(tb.done(total_tax))
    rs.move_to_end("steuer_gesamt", last=False)
    rs.move_to_end("saldo", last=False)

    for i, (text, rules) in enumerate(ctx.warnings):
        tbw = tracer.new(f"warn_{i}", text, "Text", "Hinweise und Warnungen")
        tbw.rule(*rules).flag("warnung")
        tbw.step(text)
        rs.add(tbw.done("⚠"))
    return res


def _without_alg(ps, s, tracer, rs) -> None:
    """No ALG for the person (not claimed or no exit): the result list shows no ALG entries for the person. The
    timeline is still computed (employment, KV); a hint in the warnings says why there is no ALG."""
    grp = f"ALG – {ps.title}"
    for k in [k for k, t in rs.items() if t.group == grp]:
        del rs[k]


def _latest_payment_year(s) -> int:
    """Latest possible (window) or planned payment year; at least the earliest exit year + 2."""
    leaving = [ps for ps in s.persons if ps.austritt]
    years = [(min(ps.end_date.year for ps in leaving) if leaving else s.stand.year) + 2]
    for ps in leaving:
        w = ps.window()
        years.append(w[1] // 12 if w else ps.pay_year)
    return max(years)


def _horizon(s, tracer, rs, ctx) -> None:
    """Ä1: automatic horizon up to the latest possible payment year or the end of ALG, whichever is later."""
    o = s.options
    tb = tracer.new("horizont", "Planungshorizont" + (" (automatisch)" if o.horizon_auto else ""), "Text", "Übersicht")
    tb.rule("R_Faelligkeit")
    tb.s("options.horizon_auto", "Horizont automatisch")
    if o.horizon_auto:
        pay_end = o.horizon_end
        alg_end = max((tl.alg_end.year for tl in ctx.timelines.values() if tl.alg_end), default=o.horizon_start)
        o.horizon_end = max(pay_end, alg_end)
        tb.step(f"Beginn: Jahr des frühesten Austritts {o.horizon_start}" if any(ps.austritt for ps in s.persons)
                else f"Beginn: Stand der Daten {o.horizon_start} (kein Austritt geplant)")
        tb.step(f"Ende: spätestes mögliches Zahlungsjahr {pay_end} bzw. Ende des ALG-Bezugs {alg_end} → {o.horizon_end}")
    else:
        tb.step(f"Manuell eingestellt: {o.horizon_start}–{o.horizon_end}")
    tb.step("Alle Salden werden über diesen Horizont gebildet.")
    rs.add(tb.done(f"{o.horizon_start}–{o.horizon_end}"))


def _check_window(ps, ctx) -> None:
    w = ps.window()
    if not w:
        return
    for mi, _ in ctx.payments[ps.id]:
        if not w[0] <= mi <= w[1]:
            ctx.warn(f"{ps.label}: Zahlungsmonat {mi % 12 + 1:02d}/{mi // 12} liegt außerhalb des Auszahlungsfensters "
                     f"{w[0] % 12 + 1:02d}/{w[0] // 12} – {w[1] % 12 + 1:02d}/{w[1] // 12}.", ["R_Faelligkeit"])
    ctx.warn(f"{ps.label}: Der Zahlungstermin der Abfindung muss vor Fälligkeit vertraglich vereinbart sein; "
             f"bereits fällige Beträge dürfen nicht verschoben werden.", ["R_Faelligkeit", "R_Gestaltungsrisiko"])


def _computed(ctx, fn):
    """Run ``fn(rs)`` into a separate result set; warnings are collected separately."""
    saved = ctx.warnings
    ctx.warnings = []
    tmp = ResultSet()
    try:
        units = fn(tmp)
        return units, tmp, ctx.warnings
    finally:
        ctx.warnings = saved


def _single_units(y, s, tracer, rs, ctx) -> list:
    """Single assessment: one unit per person. Household measures half each; the Basisrente goes to the
    person with the higher ordinary income first (up to the personal maximum, R_Basisrente)."""
    persons = list(enumerate(s.persons))
    share = 1.0 / len(persons)
    rv_id = tracer.legal.pick("rv_beitragssatz_gesamt", "rv_beitragssatz")
    rv_satz = tracer.legal.value(rv_id, y) if rv_id else s.options.rv_satz_annahme
    rv_bbg = tracer.p("rv_bbg_monat", y)
    hoechst = tracer.p("av_basisrente_hoechstbetrag_je_person", y)

    def ordinary(ps):
        tl = ctx.timelines[ps.id]
        return sum(tl.gross_in_year(y)) + ps.rent_for(y)[0]

    rest = basisrente_for(s, y)
    alloc = {}
    for _, ps in sorted(persons, key=lambda x: -ordinary(x[1])):
        room = max(0.0, hoechst - rv_contributions(ps, ctx.timelines[ps.id], y, rv_satz, rv_bbg))
        alloc[ps.id] = min(rest, room)
        rest -= alloc[ps.id]
    if rest > 0:  # above both maxima: stays with the first person (warning in the unit)
        first = max(persons, key=lambda x: ordinary(x[1]))[1].id
        alloc[first] += rest

    def calc(target, sa_override=None):
        return [compute_unit_year(f"{ps.id}_", [(i, ps)], y, s, tracer, target, ctx, joint=False, share=share,
                                  basis=alloc[ps.id], sa_override=sa_override) for i, ps in persons]

    units = calc(rs)
    if s.sa_haelftig:
        avg = sum(u.sa for u in units) / len(units)
        rs.clear()
        units = calc(rs, sa_override=avg)
    return units


def _tax_year(y, s, tracer, rs, ctx) -> list:
    choice = s.veranlagung_for(y)
    persons = list(enumerate(s.persons))
    if len(persons) == 1:
        return [compute_unit_year("", persons, y, s, tracer, rs, ctx, joint=s.joint)]
    variants = {}
    if choice in ("auto", "zusammen"):
        variants["zusammen"] = _computed(ctx, lambda t: [compute_unit_year("", persons, y, s, tracer, t, ctx, joint=True)])
    if choice in ("auto", "einzel"):
        variants["einzel"] = _computed(ctx, lambda t: _single_units(y, s, tracer, t, ctx))
    totals = {k: sum(u.total for u in v[0]) for k, v in variants.items()}
    chosen = min(totals, key=totals.get) if choice == "auto" else choice
    units, tmp, warns = variants[chosen]
    rs.update(tmp)
    for w in warns:
        ctx.warn(*w)

    label = {"zusammen": "Zusammenveranlagung", "einzel": "Einzelveranlagung"}
    tb = tracer.new(f"veranlagung_{y}", f"Veranlagungsart {y}", "Text", f"Steuer {y}")
    tb.rule("R_Einzelveranlagung")
    tb.s(f"veranlagung.{y}", "Wahl der Veranlagungsart (auto = günstigere)")
    for k, v in totals.items():
        detail = ""
        if k == "einzel":
            detail = " (" + ", ".join(f"{s.person(u.pids[0]).label} {fmt_eur(u.total)}" for u in variants[k][0]) + ")"
        tb.step(f"{label[k]}: Steuer {fmt_eur(v)}{detail}")
    if choice == "auto" and len(totals) == 2:
        tb.step(f"→ {label[chosen]} ist um {fmt_eur(abs(totals['zusammen'] - totals['einzel']))} günstiger "
                f"(wird mit der Steuererklärung gewählt).")
    tb.step("Einzelveranlagung lohnt sich, wenn eine Abfindung in einer Spalte mit negativem übrigem zvE steht und das "
            "Gehalt des anderen Partners das gemeinsame zvE sonst über die Nullgrenze heben würde. Sie kostet den "
            "Splittingvorteil auf das Gehalt.")
    if chosen == "einzel" and s.sa_haelftig:
        tb.step("Sonderausgaben auf gemeinsamen Antrag je zur Hälfte (§ 26a Abs. 2 EStG).")
    tb.child(*[f"steuer_{u.key}{y}" for u in units])
    rs.add(tb.done(label[chosen] + (" (automatisch)" if choice == "auto" else "")))

    if chosen == "einzel":
        tb = tracer.new(f"steuer_{y}", f"Steuer gesamt {y} (Einzelveranlagung)", "EUR", f"Steuer {y}")
        tb.rule("R_Einzelveranlagung").child(f"veranlagung_{y}", *[f"steuer_{u.key}{y}" for u in units])
        tb.step(" + ".join(f"{fmt_eur(u.total)}" for u in units) + f" = {fmt_eur(sum(u.total for u in units))}")
        rs.add(tb.done(sum(u.total for u in units)))
    return units


def _section_notes(raw, ctx) -> None:
    off = [label for key, label in SECTIONS.items() if not raw.active(key)]
    if not off:
        return
    text = "Deaktivierte Bereiche (nicht berücksichtigt): " + ", ".join(off) + "."
    if not raw.active("kv"):
        text += " Ohne KV/PV fehlen auch die Beiträge in den Vorsorgeaufwendungen."
    ctx.warn(text, [])



def _zusammenballung(ps, idx, s, tracer, rs, ctx) -> None:
    """R_Zusammenballung (the severance is paid in one amount)."""
    tb = tracer.new(f"zusammenballung_{ps.id}", f"Fünftelregelung zulässig {ps.label}", "bool", "Abfindung")
    tb.rule("R_Zusammenballung", "R_Entschaedigung")
    by_year = ctx.ae_gross[ps.id]
    total = sum(by_year.values())
    path = f"persons.{idx}.fuenftel_ok"
    derive = s.origin_of(path) == "abgeleitet"
    ok_flag = tb.s(path, "Voraussetzungen der Fünftelregelung (eigene Angabe)") if not derive else None
    if total <= 0:
        tb.step("Keine Abfindung.")
        rs.add(tb.done(False))
        if derive:
            ctx.derived[path] = (False, tb.t.id)
        return
    main_year = max(by_year, key=by_year.get)
    main = by_year[main_year]
    tb.step(f"Zahlung der Abfindung in einem Betrag: {fmt_eur(main)} in {main_year}")
    tl = ctx.timelines[ps.id]
    e = ps.end_date
    if main_year > e.year:
        # R_Zusammenballung_Folgejahr: compare the severance with the salary that would have been earned
        # in that year; basis = last full year before the exit, carried forward.
        tb.rule("R_Zusammenballung_Folgejahr")
        full = e.year if (e.month, e.day) == (12, 31) else e.year - 1
        fort = ps.annual_equiv(full)
        fy = ps.salary_for(full)[1]
        tb.s(f"persons.{idx}.salary.{fy}" if fy else f"persons.{idx}.severance", f"Jahresgehalt {full} (letztes volles Jahr)")
        ballung = main > fort
        tb.step(f"Zahlung im Jahr nach dem Austritt: Abfindung {fmt_eur(main)} {'>' if ballung else '≤'} Gehalt bei "
                f"Fortsetzung des Arbeitsverhältnisses {fmt_eur(fort)} (Jahresgehalt {full}, fortgeschrieben auf {main_year})")
    else:
        g_old, g_new = tl.gross_in_year(main_year)
        mit = g_old + g_new + main + tl.alg_in_year(main_year)
        fy = ps.salary_for(e.year)[1]
        fort = ps.annual_equiv(e.year)
        tb.s(f"persons.{idx}.salary.{fy}" if fy else f"persons.{idx}.severance", "Jahresgehalt bei Fortsetzung")
        ballung = mit > fort
        tb.step(f"Einkünfte {main_year} mit Entschädigung {fmt_eur(mit)} {'>' if ballung else '≤'} Einkünfte bei "
                f"Fortsetzung {fmt_eur(fort)} (Jahresgehalt {fy})")
    rules = ["R_Zusammenballung"] + (["R_Zusammenballung_Folgejahr"] if main_year > e.year else [])
    if derive:
        # origin "abgeleitet": determined by the program; a compensation within § 24 Nr. 1 EStG is assumed
        tb.step("Herkunft „abgeleitet“: vom Programm bestimmt. Unterstellt wird, dass die Abfindung eine Entschädigung "
                "im Sinne von § 24 Nr. 1 EStG ist (Ersatz für entgangene Einnahmen, Auflösung auf Veranlassung des "
                "Arbeitgebers); geprüft wird die Zusammenballung.")
        ok = ballung
        ctx.derived[path] = (ok, tb.t.id)
        if not ok:
            ctx.warn(f"{ps.label}: Fünftelregelung entfällt (keine Zusammenballung) – Abfindung wird regulär besteuert.",
                     rules)
    else:
        # own statement (Angabe/Annahme) is decisive; a different result of the check is reported
        tb.step(f"Eigene Angabe: Voraussetzungen {'erfüllt' if ok_flag else 'nicht erfüllt'} – maßgeblich für die Rechnung.")
        ok = bool(ok_flag)
        if ok and not ballung:
            ctx.warn(f"{ps.label}: Laut Angabe ist die Fünftelregelung anwendbar, die Prüfung ergibt aber keine "
                     f"Zusammenballung. Gerechnet wird mit der Angabe.", rules)
        if not ok:
            ctx.warn(f"{ps.label}: Fünftelregelung laut Angabe nicht anwendbar – Abfindung wird regulär besteuert.",
                     rules)
    for y in by_year:
        ctx.priv[(ps.id, y)] = ok and y == main_year
    tb.step("→ " + ("Fünftelregelung" if ok else "keine Fünftelregelung"))
    rs.add(tb.done(ok))


def _measure_warnings(s, ctx, tracer) -> None:
    kinds = {g.typ for _, g in gestaltungen(s) if g.betrag or g.kaufpreis}
    if "erhaltung" in kinds and s.objekte_angeschafft_3j:
        ctx.warn("Erhaltungsaufwand an Objekten, die in den letzten 3 Jahren angeschafft wurden: Prüfung "
                 "anschaffungsnaher Herstellungskosten.", ["R_Erhaltung"])
    if kinds & {"erhaltung", "kauf", "spende", "sonstige"}:
        ctx.warn("Gestaltungen müssen wirtschaftlich sinnvoll sein; reine Steuersparmodelle werden nicht anerkannt.",
                 ["R_Grenzen_Gestaltung"])


def run_comparable(settings_list, legal, extras: bool = False) -> list:
    """Run several settings over one common horizon so that their Saldo values are comparable."""
    results = [run(t, legal, extras=extras) for t in settings_list]
    start = min(r.years[0] for r in results)
    end = max(r.years[-1] for r in results)
    out = []
    for t, r in zip(settings_list, results):
        if (r.years[0], r.years[-1]) != (start, end):
            t = t.copy()
            t.options.horizon_auto = False
            t.options.horizon_start, t.options.horizon_end = start, end
            r = run(t, legal, extras=extras)
        out.append(r)
    return out
