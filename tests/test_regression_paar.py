"""Regression values of the fictitious couple (tests/fixtures/fiktiv_paar.xml).

Snapshot of the tool's results across the payment cases A/E/F and the registration cases S1/S2 (see
tests/helpers.py), with and without a new job of P2 from 2029 and per assessment type. The values were
checked for plausibility when the data set was created; a change shows that the calculation changed.
Tolerance: 1 €.
"""

from datetime import date
from pathlib import Path

import pytest

from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal
from abfindung.io import load_legal, load_personal

from .helpers import apply_scenario, apply_variant, set_basisrente

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "fiktiv_paar.xml"
from abfindung import LEGAL_XML as LEGAL  # noqa: E402
YEARS = (2027, 2028, 2029)
TOL = 1.0


@pytest.fixture(scope="module")
def legal():
    return load_legal(LEGAL)


def setup(legal, variant, scenario, job=False, mode=None, basisrente=None, joint27=False):
    s = from_personal(load_personal(FIXTURE), legal)
    if joint27:  # 2027 as joint assessment (one tax unit), for the unit-level checks
        s.veranlagung[2027] = "zusammen"
    s.options.horizon_auto = False
    s.options.horizon_start, s.options.horizon_end = 2027, 2029
    apply_variant(s, variant)
    apply_scenario(s, scenario)
    if job:  # P2 works again from 2029
        p2 = s.persons[1]
        p2.newjob, p2.newjob_start, p2.newjob_salary = True, date(2029, 1, 1), 85_000
    if mode:
        s.veranlagung[2029] = mode
    if basisrente:
        set_basisrente(s, dict(basisrente))
    return s


BELASTUNG = [  # (variant, scenario, P2 job 2029, assessment 2029, tax (2027, 2028, 2029))
    ("A", "S1", False, None, (91_701, 0, 0)),
    ("E", "S1", False, None, (56_128, 4_858, 0)),
    ("F", "S1", False, None, (35_660, 6_990, 0)),
    ("A", "S2", False, None, (84_603, 0, 0)),
    ("E", "S2", False, None, (50_368, 2_502, 0)),
    ("F", "S2", False, None, (31_905, 6_783, 0)),
    ("A", "S1", True, 'auto', (91_701, 0, 11_269)),
    ("F", "S1", True, 'zusammen', (35_660, 6_990, 11_269)),
    ("F", "S1", True, 'einzel', (35_660, 6_990, 18_533)),
    ("E", "S1", True, 'zusammen', (56_128, 4_858, 11_269)),
    ("E", "S1", True, 'einzel', (56_128, 4_858, 18_533)),
]


@pytest.mark.parametrize("variant,scenario,job,mode,ref", BELASTUNG,
                         ids=[f"{v}-{s}{'-job-' + str(m) if j else ''}" for v, s, j, m, _ in BELASTUNG])
def test_belastung(legal, variant, scenario, job, mode, ref):
    r = run(setup(legal, variant, scenario, job, mode), legal, extras=False)
    for year, want in zip(YEARS, ref):
        assert r.tax_by_year[year] == pytest.approx(want, abs=TOL), year


def test_sum_a_s1(legal):
    r = run(setup(legal, "A", "S1"), legal, extras=False)
    assert sum(r.tax_by_year[y] for y in YEARS) == pytest.approx(91_701, abs=TOL)


@pytest.mark.parametrize("deduction,want", [(0, 92_085), (5_000, 87_362), (10_000, 82_511), (15_000, 77_305), (20_000, 71_266), (25_000, 63_646), (30_000, 55_264)])
def test_abzugswirkung_2027_a_s1(legal, deduction, want):
    u = run(setup(legal, "A", "S1", joint27=True), legal, extras=False).units[("", 2027)]
    assert u.tax_for(deduction) == pytest.approx(want, abs=TOL)


def test_nullgrenze_2027(legal):
    u = run(setup(legal, "A", "S1", joint27=True), legal, extras=False).units[("", 2027)]
    assert u.v + u.pv == pytest.approx(47_313, abs=TOL)


@pytest.mark.parametrize("variant,want", [("A", 56_828), ("E", 45_587), ("F", 29_444)])
def test_ersparnis_basisrente_2027(legal, variant, want):
    without = run(setup(legal, variant, "S1", joint27=True), legal, extras=False).tax_by_year[2027]
    with_br = run(setup(legal, variant, "S1", basisrente={2027: 47_300}, joint27=True), legal,
                  extras=False).tax_by_year[2027]
    assert without - with_br == pytest.approx(want, abs=TOL)


def test_nullgrenze_2029_e_job(legal):
    u = run(setup(legal, "E", "S1", True, "zusammen"), legal, extras=False).units[("", 2029)]
    assert u.v + u.pv == pytest.approx(72_470, abs=TOL)


@pytest.mark.parametrize("variant,mode,want", [("E", "zusammen", 201), ("F", "einzel", 12_656)])
def test_steuer_2029_mit_basisrente(legal, variant, mode, want):
    r = run(setup(legal, variant, "S1", True, mode, {2029: 72_500}), legal, extras=False)
    assert r.tax_by_year[2029] == pytest.approx(want, abs=TOL)


@pytest.mark.parametrize("variant,mode,want", [("E", "zusammen", 15_600), ("F", "einzel", 25_862), ("A", "auto", 35_458)])
def test_summe_mit_basisrente_job(legal, variant, mode, want):
    r = run(setup(legal, variant, "S1", True, mode, {2027: 47_300, 2029: 72_500}), legal, extras=False)
    assert sum(r.tax_by_year[y] for y in YEARS) == pytest.approx(want, abs=TOL)


def test_childcare_only_partly_deductible(legal):
    """Childcare costs count with kind_betreuung_anteil only (one child under 14 in 2027)."""
    r = run(setup(legal, "A", "S1", joint27=True), legal, extras=False)
    steps = " ".join(r.rs["sa_2027"].steps)
    assert "Kinderbetreuung" in steps and "1 Kinder unter 14" in steps
