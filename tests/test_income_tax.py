"""Annual tax tests: Günstigerprüfung, Soli, Basisrente, bAV, scenario (synthetic data)."""

import pytest

from abfindung.engine.payroll import soli_on
from abfindung.engine.scenario import run
from abfindung.engine.settings import add_gestaltung, from_personal
from abfindung.engine.trace import Tracer

from .helpers import set_basisrente


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_scenario_runs(s, legal):
    r = run(s, legal)
    assert r.years == [2026, 2027, 2028]
    for y in r.years:
        assert f"steuer_{y}" in r.rs and f"saldo_{y}" in r.rs
    assert r.rs["saldo"].value == pytest.approx(sum(r.saldo_by_year.values()))
    # every result is explainable
    for t in r.rs.values():
        assert t.steps, t.id


def test_guenstigerpruefung_low_vs_high_income(s, legal):
    for ps in s.persons:
        ps.salary = {2025: 0.0}
        ps.severance = 0.0
        ps.rent = {2025: 0.0}
        ps.sperrzeit_wochen = 0
        ps.alg_monat = 0.0
    s.childcare = {}
    r = run(s, legal)
    u = r.units[("", 2027)]
    assert not u.fb_gewaehlt  # Kindergeld is better for low income
    for ps in s.persons:
        ps.salary = {2025: 250_000.0}
        ps.end_date = ps.end_date.replace(year=2030)
    s.options.horizon_auto = False  # keep 2026–2028
    r = run(s, legal)
    u = r.units[("", 2027)]
    assert u.fb_gewaehlt
    assert u.est > 0


def test_soli_always_with_child_allowance(s, legal):
    r = run(s, legal)
    u = r.units[("", 2026)]
    assert "ESt mit Kinderfreibeträgen" in r.rs["soli_2026"].steps[0]
    assert u.kfb > 0


def test_soli_exemption_and_continuity(legal):
    tr = Tracer(legal)
    fg = legal.value("soli_freigrenze_zusammen", 2026)
    assert soli_on(fg, True, 2026, tr) == 0
    assert soli_on(fg + 1, True, 2026, tr) == pytest.approx(legal.value("soli_milderungssatz"))
    prev = 0
    for x in range(int(fg), int(fg * 2), 50):
        v = soli_on(x, True, 2026, tr)
        assert v >= prev and v - prev <= 50 * legal.value("soli_milderungssatz") + 1e-6
        prev = v
    assert soli_on(1e6, True, 2026, tr) == pytest.approx(1e6 * legal.value("soli_satz"))


def _vorsorge(s, legal, year=2027):
    return run(s, legal, extras=False).rs[f"vorsorge_{year}"].value


def test_basisrente_reduced_by_rv_and_doubled_when_joint(s, legal):
    s.veranlagung[2026] = "zusammen"
    base = _vorsorge(s, legal, 2026)
    set_basisrente(s, {2026: 200_000})  # both persons employed and RV-insured
    full = _vorsorge(s, legal, 2026)
    r = run(s, legal, extras=False)
    u = r.units[("", 2026)]
    hoechst = legal.value("av_basisrente_hoechstbetrag_je_person", 2026)
    assert u.rv_total > 0
    assert full - base == pytest.approx(2 * hoechst - u.rv_total, abs=1)
    s.veranlagung[2026] = "einzel"
    r = run(s, legal, extras=False)
    tot = 0
    for ps in s.persons:
        u = r.units[(f"{ps.id}_", 2026)]
        tot += u.basisrente_abzug
        assert u.basisrente_abzug <= hoechst - u.rv_total + 1


def test_payment_year_shifts_tax(s, legal):
    r_a = run(s, legal, extras=False)
    s.persons[0].pay_idx = 2026 * 12 + 11  # December 2026
    r_b = run(s, legal, extras=False)
    assert r_b.tax_by_year[2026] > r_a.tax_by_year[2026]
    assert r_b.tax_by_year[2027] < r_a.tax_by_year[2027]


def test_deduction_marginal_effect(s, legal):
    r = run(s, legal, extras=False)
    u = r.main_unit_year()
    assert u.ae > 0
    ng = max(0.0, u.v + u.pv)
    if ng > 2000:
        before = u.tax_for(0) - u.tax_for(1000)
        after = u.tax_for(ng + 1000) - u.tax_for(ng + 2000)
        assert before > after


def test_liquidity_and_refund(s, legal):
    r = run(s, legal)
    assert len(r.liquidity) == 36
    assert "liq_min" in r.rs
    assert r.rs["lst_abf_P_Erika"].value > 0


def test_property_purchase(s, legal):
    gid = add_gestaltung(s, "kauf", 2027, kaufpreis=300_000, darlehen=250_000, miete_jahr=11_000,
                         ortsuebliche_miete_jahr=11_000, kauf_erhaltung=100_000)  # > 15 % -> anschaffungsnah
    r = run(s, legal)
    assert any("anschaffungsnahe" in w[0] for w in r.warnings)
    assert r.cost_by_year[2027] == 0 and r.gebunden != 0  # default: running costs fully counter-valued
    s.measures.items[gid].gegenwert = 0.0
    assert run(s, legal).cost_by_year[2027] != 0


def test_calibration(s, legal):
    r = run(s, legal)
    assert "kalibrierung" in r.rs
    assert r.extra.get("vorsorge_faktor_vorschlag", 0) > 0


def test_total_tax_in_overview(s, legal):
    r = run(s, legal, extras=False)
    t = r.rs["steuer_gesamt"]
    assert t.group == "Übersicht" and t.value == pytest.approx(sum(r.tax_by_year.values()))
    assert list(r.rs)[:2] == ["saldo", "steuer_gesamt"]
