# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Optimisation.

Search space:
  * payment month per person: current month, December of the exit year,
    January of the following year(s) (with a payment window: every year in it)
  * exit per person: planned end and the XML alternatives (e.g. Freistellung)
  * registration date per person: earliest possible, start of month, one-year limit
    + 7 days buffer, XML scenario dates
  * continuous: Basisrente 0 … maximum (500 € steps, golden section), Erhaltungsaufwand
    0 … upper limit
Discrete options are enumerated completely; continuous ones are optimised per top
candidate. The Nullgrenze (deduction at which v + PV = 0) is reported separately.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..dates import add_months, add_years, fmt_date, fmt_eur, fmt_month, month_index
from .health import severance_allocation, severance_extra
from .scenario import run
from .settings import (GESTALTUNG_TYPEN, Settings, apply_exit, effective, gestaltungen,
                       set_basisrente_year)

GOLD = (math.sqrt(5) - 1) / 2


@dataclass
class Candidate:
    label: str
    changes: dict
    saldo: float = 0.0
    tax_by_year: dict = field(default_factory=dict)
    alg: float = 0.0
    kv: float = 0.0
    cost: float = 0.0
    gebunden: float = 0.0
    liq_min: float = 0.0
    explanation: str = ""
    rules: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _apply(s: Settings, changes: dict) -> Settings:
    t = s.copy()
    for path, v in changes.items():
        if path.startswith("exit."):
            apply_exit(t, int(path.split(".")[1]), v)
        elif path.startswith("basisrente."):
            set_basisrente_year(t, int(path.split(".")[1]), v)
        else:
            t.set(path, v)
    return t


def _meldung_options(s: Settings, i: int, end: date, freistellung_ab: date | None) -> list[tuple[str, date]]:
    first = end + timedelta(days=1)
    opts = [("frühestmöglich", first)]
    mstart = first if first.day == 1 else add_months(first.replace(day=1), 1)
    opts.append(("Monatsanfang", mstart))
    ereignis = freistellung_ab if (s.options.ein_jahres_ereignis == "freistellung" and freistellung_ab) else end
    opts.append(("Ein-Jahres-Grenze + 7 Tage", add_years(ereignis, 1) + timedelta(days=8)))
    seen, out = set(), []
    for lab, d in opts:
        if d not in seen:
            seen.add(d)
            out.append((lab, d))
    return out


def _payment_options(s: Settings, i: int, horizon: tuple[int, int] | None, end: date | None = None) -> list[int]:
    """Payment months to try. With a payment window (Ä1) every year in the window is searched; months within
    a year are equivalent for tax, so one month per year is used (the earliest; see _best_month for KV)."""
    ps = s.persons[i]
    end = end or ps.end_date
    if ps.fenster_aktiv:
        lo = ps.fenster_ab_idx
        hi = month_index(end.year, end.month) + ps.fenster_monate
        return [max(lo, month_index(y, 1)) for y in range(lo // 12, hi // 12 + 1)]
    ey = end.year
    opts = {ps.pay_idx, month_index(ey, 12), month_index(ey + 1, 1), month_index(ey + 2, 1)}
    if horizon is None:
        return sorted(opts)
    lo, hi = month_index(horizon[0], 1), month_index(horizon[1], 12)
    return sorted(o for o in opts if lo <= o <= hi)


def _exit_options(s: Settings, i: int) -> list[tuple[str, date, date | None]]:
    # The exit date is always the planned end (no Freistellung variants since the simplification).
    return [("aktuell", s.persons[i].end_date, None)]


def _best_months(s: Settings, i: int, legal, ex_id: str, meldung: date) -> list[int]:
    """Ä6: one payment month per year of the window – the month with the lowest extra KV contribution,
    the earliest on a tie (liquidity). Months within a year are equivalent for tax."""
    t = s.copy()
    if ex_id != "aktuell":
        apply_exit(t, i, ex_id)
    t.persons[i].meldung = meldung
    r = run(t, legal, extras=False)
    ps = r.settings.persons[i]
    tl, kv = r.ctx.timelines[ps.id], r.ctx.kv[ps.id]
    lo, hi = ps.window()
    amount = ps.severance
    best: dict[int, tuple[float, int]] = {}
    for mi in range(lo, hi + 1):
        alloc = severance_allocation(ps, tl, r.settings, r.tracer, [(mi, amount)])
        cost = round(sum(severance_extra(kv, alloc).values()), 2)
        y = mi // 12
        if y not in best or (cost, mi) < best[y]:
            best[y] = (cost, mi)
    return [best[y][1] for y in sorted(best)]


def enumerate_discrete(s: Settings, legal=None) -> list[dict]:
    """All discrete combinations; only persons and the horizon that enter the calculation."""
    eff = effective(s, legal) if legal is not None else s
    horizon = None if eff.options.horizon_auto else (eff.options.horizon_start, eff.options.horizon_end)
    per_person = []
    for i, ps in enumerate(s.persons[:len(eff.persons)]):
        if not ps.austritt:
            per_person.append([{"_lab": f"{ps.label}: kein Austritt"}])
            continue
        opts = []
        pay_free = is_free(s, f"persons.{i}.pay_idx")
        mel_free = ps.alg_aktiv and is_free(s, f"persons.{i}.meldung")
        for ex_id, end, fab in _exit_options(s, i):
            melds = _meldung_options(s, i, end, fab) if mel_free else [("fest", ps.meldung)]
            for mlab, md in melds:
                if not pay_free:
                    pays = [ps.pay_idx]
                elif ps.fenster_aktiv and legal is not None:
                    pays = _best_months(s, i, legal, ex_id, md)
                else:
                    pays = _payment_options(s, i, horizon, end)
                for pay in pays:
                    ch = {}
                    if pay_free:
                        ch[f"persons.{i}.pay_idx"] = pay
                    if mel_free:
                        ch[f"persons.{i}.meldung"] = md
                    if ex_id != "aktuell":
                        ch[f"exit.{i}"] = ex_id
                    ch["_lab"] = f"{ps.label}: Abfindung {fmt_month(pay // 12, pay % 12 + 1)}" \
                                 f"{'' if pay_free else ' (fest)'}, " \
                                 + (f"Meldung {fmt_date(md)} ({mlab})" if ps.alg_aktiv else "kein ALG")
                    opts.append(ch)
        per_person.append(opts)
    combos = []
    for combo in itertools.product(*per_person):
        ch, labs = {}, []
        for c in combo:
            c = dict(c)
            labs.append(c.pop("_lab"))
            ch.update(c)
        ch["_lab"] = "; ".join(labs)
        combos.append(ch)
    return combos


def _common_horizon(s: Settings, legal, combos: list[dict]) -> Settings:
    """One fixed horizon for all candidates (Saldo values must cover the same years): from the current
    horizon up to the latest payment year or registration year + 2 (end of ALG) of any candidate."""
    base = run(s, legal, extras=False)
    end = base.years[-1]
    for ch in combos:
        for k, v in ch.items():
            if k.endswith("pay_idx"):
                end = max(end, v // 12)
            elif k.endswith("meldung"):
                end = max(end, v.year + 2)
    t = s.copy()
    t.options.horizon_auto = False
    t.options.horizon_start, t.options.horizon_end = base.years[0], end
    return t


def _evaluate(s: Settings, legal, changes: dict) -> tuple[float, object]:
    ch = {k: v for k, v in changes.items() if not k.startswith("_")}
    r = run(_apply(s, ch), legal, extras=False)
    return r.saldo, r


def golden_section(f, lo: float, hi: float, step: float = 500.0, iters: int = 14) -> tuple[float, float]:
    """Maximise a unimodal f on [lo, hi]; result rounded to ``step``."""
    if hi <= lo:
        return lo, f(lo)
    cache = {}

    def g(x):
        x = round(x / step) * step
        if x not in cache:
            cache[x] = f(x)
        return cache[x]

    a, b = lo, hi
    c = b - GOLD * (b - a)
    d = a + GOLD * (b - a)
    for _ in range(iters):
        if b - a <= step:
            break
        if g(c) >= g(d):
            b = d
        else:
            a = c
        c = b - GOLD * (b - a)
        d = a + GOLD * (b - a)
    cands = [lo, hi, (a + b) / 2]
    best = max(cands, key=g)
    return round(best / step) * step, g(best)


def is_free(s: Settings, path: str) -> bool:
    """Only values with origin "planung" are varied by the optimiser."""
    return s.origin_of(path) == "planung"


OPTIMISED = [("pay_idx", "Zahlungsmonat der Abfindung"), ("meldung", "Arbeitslosmeldung")]


def fixed_values(s: Settings, legal) -> list[str]:
    """Optimisation parameters that stay fixed because their origin is not "Planung"."""
    eff = effective(s, legal)
    out = [f"{ps.label}: {lab}" for i, ps in enumerate(s.persons[:len(eff.persons)])
           for f, lab in OPTIMISED if ps.austritt and (ps.alg_aktiv or f != "meldung")
           and not is_free(s, f"persons.{i}.{f}")]
    out += [f"Basisrente {y}" for y in s.years() if not basisrente_year_free(s, y)]
    out += [g.label for gid, g in gestaltungen(s, "erhaltung") if not is_free(s, f"measures.items.{gid}.betrag")]
    return out


def basisrente_year_free(s: Settings, year: int) -> bool:
    """The optimiser may set the Basisrente of a year: no entry with a fixed amount (origin ≠ Planung)."""
    return all(is_free(s, f"measures.items.{gid}.betrag") for gid, _ in gestaltungen(s, "basisrente", year))


def basisrente_gegenwert(s: Settings, year: int) -> float:
    planned = [g for gid, g in gestaltungen(s, "basisrente", year)]
    return planned[0].gegenwert if planned else GESTALTUNG_TYPEN["basisrente"][2]


def basisrente_to_zero_limit(s: Settings, legal, step: float = 100.0) -> dict:
    """Ä7: Basisrente per year up to the Nullgrenze of that year, capped by the remaining maximum
    (R_Basisrente); only years without a fixed Basisrente entry. Returns changes {"basisrente.<year>": amount}
    (applied with set_basisrente_year: the planned entry of the year, created if there is none)."""
    t = s.copy()
    for y in t.years():
        if basisrente_year_free(t, y):
            set_basisrente_year(t, y, 0.0)
    r = run(t, legal, extras=False)
    out = {}
    for y in r.years:
        if not basisrente_year_free(s, y):
            continue
        units = [u for (k, yy), u in r.units.items() if yy == y]
        ng = sum(max(0.0, u.v + u.pv) for u in units)
        room = sum(u.av_frei for u in units)
        out[f"basisrente.{y}"] = math.floor(min(ng, room) / step) * step
    return out


def _basisrente_tradeoff(s: Settings, legal, ch: dict) -> dict:
    """With a Gegenwert below 100 % a euro of Basisrente costs (1 − Gegenwert) in the Saldo: search each year
    between 0 and the Nullgrenze amount for the best trade-off with the tax saving (coordinate-wise)."""
    out = {}
    for k in sorted(k for k in ch if k.startswith("basisrente.")):
        if basisrente_gegenwert(s, int(k.split(".")[1])) >= 1:
            continue
        hi = ch[k]

        def f(x, k=k):
            return _evaluate(s, legal, {**ch, **out, k: x})[0]
        out[k], _ = golden_section(f, 0.0, hi)
    return out


def optimize(s: Settings, legal, opt_basisrente: bool = True, opt_erhaltung: bool = False,
             top_n: int = 5, progress=None, should_stop=None) -> tuple[list[Candidate], Candidate]:
    """Returns (top candidates, current settings as candidate)."""
    if not s.active("gestaltungen"):
        opt_basisrente = opt_erhaltung = False
    combos = enumerate_discrete(s, legal)
    s = _common_horizon(s, legal, combos)
    base_res = run(s, legal)
    current = _summarize("Aktuelle Einstellung", {}, base_res)
    scored = []
    total = len(combos)
    for k, ch in enumerate(combos):
        if should_stop and should_stop():
            break
        saldo, _ = _evaluate(s, legal, ch)
        scored.append((saldo, ch))
        if progress and k % 10 == 0:
            progress(k, total + 10 * top_n)
    # deduplicate identical outcomes, keep best
    scored.sort(key=lambda x: -x[0])
    shortlist = scored[: max(top_n * 3, 10)]
    final = []
    for j, (_, ch) in enumerate(shortlist):
        if should_stop and should_stop():
            break
        ch = dict(ch)
        trial = _apply(s, {k: v for k, v in ch.items() if not k.startswith("_")})
        if opt_basisrente:
            ch.update(basisrente_to_zero_limit(trial, legal))
            ch.update(_basisrente_tradeoff(s, legal, ch))
        if opt_erhaltung:
            for gid, g in gestaltungen(s, "erhaltung"):
                path = f"measures.items.{gid}.betrag"
                hi = max(s.erhaltung_max, g.betrag)
                if not is_free(s, path) or hi <= 0:
                    continue

                def fe(x, ch=ch, path=path):
                    return _evaluate(s, legal, {**ch, path: x})[0]
                ch[path], _ = golden_section(fe, 0.0, hi)
        res = run(_apply(s, {k: v for k, v in ch.items() if not k.startswith("_")}), legal)  # incl. liquidity
        final.append(_summarize(ch.get("_lab", ""), ch, res))
        if progress:
            progress(total + 10 * (j + 1), total + 10 * len(shortlist))
    final.sort(key=lambda c: -c.saldo)
    seen, top = set(), []
    for c in final:
        key = round(c.saldo, 0)
        if key in seen:
            continue
        seen.add(key)
        top.append(c)
        if len(top) >= top_n:
            break
    for c in top:
        c.explanation, c.rules = explain_candidate(c, current, s)
    return top, current


def _summarize(label: str, changes: dict, r) -> Candidate:
    c = Candidate(label, {k: v for k, v in changes.items() if not k.startswith("_")})
    c.saldo = r.saldo
    c.tax_by_year = dict(r.tax_by_year)
    c.alg = sum(r.alg_by_year.values())
    c.kv = sum(r.kv_by_year.values())
    c.cost = sum(r.cost_by_year.values())
    c.gebunden = r.gebunden
    c.liq_min = r.liq_min
    c.extra = {"sal": sum(r.salary_by_year.values()), "horizont": (r.years[0], r.years[-1])}
    return c


def explain_candidate(c: Candidate, base: Candidate, s: Settings) -> tuple[str, list]:
    lines, rules = [], set()
    d = c.saldo - base.saldo
    lines.append(f"Saldo {fmt_eur(c.saldo)} ({'+' if d >= 0 else ''}{fmt_eur(d)} gegenüber der aktuellen Einstellung).")
    for y in sorted(c.tax_by_year):
        dt = c.tax_by_year[y] - base.tax_by_year.get(y, 0)
        if abs(dt) >= 1:
            lines.append(f"Steuer {y}: {fmt_eur(c.tax_by_year[y])} ({'+' if dt >= 0 else ''}{fmt_eur(dt)}).")
    if abs(c.alg - base.alg) >= 1:
        lines.append(f"ALG im Horizont {fmt_eur(c.alg)} ({'+' if c.alg >= base.alg else ''}{fmt_eur(c.alg - base.alg)}).")
        rules.update({"R_ALG_Dauer", "R_Parallel"})
    if abs(c.kv - base.kv) >= 1:
        lines.append(f"Eigene KV/PV {fmt_eur(c.kv)} ({'+' if c.kv >= base.kv else ''}{fmt_eur(c.kv - base.kv)}).")
        rules.update({"R_KV_ALG", "R_KV_RuhenAbfindung"})
    for path, v in c.changes.items():
        if path.endswith("pay_idx"):
            i = int(path.split(".")[1])
            if v != s.persons[i].pay_idx:
                lines.append(f"{s.persons[i].label}: Abfindung im {fmt_month(v // 12, v % 12 + 1)} statt "
                             f"{fmt_month(s.persons[i].pay_year, s.persons[i].pay_month)} – Zuflussjahr mit niedrigerem "
                             f"übrigen Einkommen bzw. weniger ALG im Progressionsvorbehalt.")
                rules.update({"R_Zufluss", "R_Fuenftel_Progressionsvorbehalt"})
        elif path.endswith("meldung"):
            i = int(path.split(".")[1])
            if v != s.persons[i].meldung:
                lines.append(f"{s.persons[i].label}: Arbeitslosmeldung am {fmt_date(v)} statt {fmt_date(s.persons[i].meldung)}.")
                rules.update({"R_ALG_Dauer", "R_Progressionsvorbehalt"})
        elif path.startswith("basisrente.") and v:
            lines.append(f"Basisrente {fmt_eur(v)} in {path.rsplit('.', 1)[1]}: bis zur Nullgrenze dieses Jahres wirkt der "
                         f"Abzug fast vollständig. Gebunden bis Rentenbeginn, später voll steuerpflichtig.")
            rules.update({"R_Basisrente", "R_Fuenftel_Progressionsvorbehalt"})
        elif path.startswith("measures.items.") and path.endswith(".betrag"):
            g = s.measures.items.get(path.split(".")[2])
            if g is not None and g.typ == "erhaltung" and abs(v - g.betrag) >= 1:
                lines.append(f"{g.label}: {fmt_eur(v)} statt {fmt_eur(g.betrag)} – nur sinnvoll, wenn ohnehin nötig.")
                rules.update({"R_Erhaltung", "R_Grenzen_Gestaltung"})
    if c.liq_min < base.liq_min - 1:
        lines.append(f"Achtung Liquidität: Tiefpunkt {fmt_eur(c.liq_min)}.")
    return "\n".join(lines), sorted(rules)
