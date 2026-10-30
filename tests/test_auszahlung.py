"""Ä1/Ä2: payment window, automatic horizon, reference variants, Zusammenballung in a later year."""

from pathlib import Path

import pytest

from abfindung.dates import month_index
from abfindung.engine.optimizer import enumerate_discrete
from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal
from abfindung.io import load_personal

FIXTURE = Path(__file__).parent / "fixtures" / "fiktiv_paar.xml"


@pytest.fixture()
def paar(legal):
    return from_personal(load_personal(FIXTURE), legal)


def test_window_from_xml(paar):
    p1 = paar.persons[0]
    assert p1.fenster_aktiv and p1.window() == (month_index(2027, 8), month_index(2030, 2))


def test_horizon_reaches_latest_payment_year(paar, legal):
    r = run(paar, legal, extras=False)
    assert r.years == [2027, 2028, 2029, 2030]
    paar.options.horizon_auto = False
    paar.options.horizon_start, paar.options.horizon_end = 2026, 2028
    assert run(paar, legal, extras=False).years == [2026, 2027, 2028]


def test_payment_outside_window_warns(paar, legal):
    paar.persons[0].pay_idx = month_index(2031, 1)
    r = run(paar, legal, extras=False)
    assert any("außerhalb des Auszahlungsfensters" in w for w, _ in r.warnings)


def test_optimizer_searches_window_years(paar, legal):
    years = {c["persons.0.pay_idx"] // 12 for c in enumerate_discrete(paar, legal)}
    assert {2027, 2028, 2029, 2030} <= years


def test_zusammenballung_following_year(paar, legal):
    p1 = paar.persons[0]
    paar.set_origin("persons.0.fuenftel_ok", "abgeleitet")  # determined by the program
    p1.pay_idx = month_index(2028, 1)
    r = run(paar, legal, extras=False)
    assert r.rs["zusammenballung_P1"].value is True
    p1.severance = 30_000  # below the salary of the last full year (2026: 52.000)
    r = run(paar, legal, extras=False)
    assert r.rs["zusammenballung_P1"].value is False
    assert "R_Zusammenballung_Folgejahr" in r.rs["zusammenballung_P1"].rules
    assert any("Fünftelregelung entfällt" in w for w, _ in r.warnings)
    assert r.ctx.derived["persons.0.fuenftel_ok"][0] is False


def test_fifth_rule_own_statement_is_decisive(paar, legal):
    p1 = paar.persons[0]
    p1.pay_idx = month_index(2028, 1)
    p1.severance = 30_000  # check fails ...
    paar.set_origin("persons.0.fuenftel_ok", "angabe")
    p1.fuenftel_ok = True  # ... but the user states the prerequisites are met
    r = run(paar, legal, extras=False)
    assert r.rs["zusammenballung_P1"].value is True
    assert any("ergibt aber keine Zusammenballung" in w for w, _ in r.warnings)
    assert "persons.0.fuenftel_ok" not in r.ctx.derived
    p1.fuenftel_ok = False
    assert run(paar, legal, extras=False).rs["zusammenballung_P1"].value is False
