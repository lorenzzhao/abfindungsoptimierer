"""Ä3: joint or single assessment per year (R_Einzelveranlagung)."""

from datetime import date
from pathlib import Path

import pytest

from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal
from .helpers import apply_scenario, apply_variant
from abfindung.io import load_personal

FIXTURE = Path(__file__).parent / "fixtures" / "fiktiv_paar.xml"


@pytest.fixture()
def paar(legal):
    return from_personal(load_personal(FIXTURE), legal)


def _tax(s, legal, year, mode):
    s.veranlagung[year] = mode
    return run(s, legal, extras=False).tax_by_year[year]


def test_splitting_advantage_without_severance(paar, legal):
    paar.options.horizon_auto = False
    paar.options.horizon_start, paar.options.horizon_end = 2026, 2028
    for ps in paar.persons:
        ps.severance = 0.0
    assert _tax(paar, legal, 2026, "einzel") >= _tax(paar, legal, 2026, "zusammen")  # both employed all year


def test_single_assessment_can_be_cheaper(paar, legal):
    """Case F, scenario 1, P2 works from 2028: severance of P1 in the column with negative v."""
    apply_variant(paar, "F")
    apply_scenario(paar, "S1")
    p2 = paar.persons[1]
    p2.newjob, p2.newjob_start, p2.newjob_salary = True, date(2028, 1, 1), 80_000
    einzel = _tax(paar, legal, 2028, "einzel")
    zusammen = _tax(paar, legal, 2028, "zusammen")
    assert einzel < zusammen
    paar.veranlagung[2028] = "auto"
    r = run(paar, legal, extras=False)
    assert r.tax_by_year[2028] == pytest.approx(einzel)
    assert r.rs["veranlagung_2028"].value.startswith("Einzelveranlagung")
    assert ("P1_", 2028) in r.units and ("P2_", 2028) in r.units


def test_single_assessment_uses_single_parameters(paar, legal):
    paar.veranlagung[2027] = "einzel"
    r = run(paar, legal, extras=False)
    u = r.units[("P1_", 2027)]
    per_child = (legal.value("kind_freibetrag_saechlich_je_elternteil", 2027)
                 + legal.value("kind_freibetrag_bea_je_elternteil", 2027))
    assert u.kfb == pytest.approx(2 * per_child)  # K1 (born 2009) is 18 in 2027
    assert u.params["soli_fg"] == legal.value("soli_freigrenze_einzeln", 2027)
    assert not u.joint


def test_special_expenses_half_each(paar, legal):
    paar.veranlagung[2027] = "einzel"
    paar.sa_haelftig = True
    r = run(paar, legal, extras=False)
    a, b = r.units[("P1_", 2027)].sa, r.units[("P2_", 2027)].sa
    assert a == pytest.approx(b)


def test_choice_roundtrip(paar, legal, tmp_path):
    from abfindung.engine.settings import to_personal
    from abfindung.io.personal_writer import save_personal

    paar.veranlagung[2028] = "einzel"
    paar.sa_haelftig = True
    out = save_personal(to_personal(paar, load_personal(FIXTURE)), tmp_path / "v.xml")
    s2 = from_personal(load_personal(out), legal)
    assert s2.veranlagung[2028] == "einzel" and s2.sa_haelftig
