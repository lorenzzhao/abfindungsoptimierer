"""Ä7: Basisrente per year and Nullgrenze per year."""

from pathlib import Path

import pytest

from abfindung.engine.optimizer import basisrente_to_zero_limit
from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal
from .helpers import apply_scenario, apply_variant, basisrente_by_year, set_basisrente
from abfindung.io import load_personal

FIXTURE = Path(__file__).parent / "fixtures" / "fiktiv_paar.xml"


@pytest.fixture()
def paar(legal):
    s = from_personal(load_personal(FIXTURE), legal)
    apply_variant(s, "E")
    apply_scenario(s, "S1")
    return s


def test_nullgrenze_every_year(paar, legal):
    r = run(paar, legal, extras=False)
    for y in r.years:
        assert any(k.startswith("nullgrenze_") and k.endswith(str(y)) for k in r.rs)


def test_basisrente_in_two_years(paar, legal):
    base = run(paar, legal, extras=False)
    set_basisrente(paar, {2027: 10_000, 2028: 10_000})
    r = run(paar, legal, extras=False)
    assert r.tax_by_year[2027] < base.tax_by_year[2027]
    assert r.tax_by_year[2028] <= base.tax_by_year[2028]
    assert r.gebunden == pytest.approx(20_000)


def test_basisrente_up_to_zero_limit(paar, legal):
    changes = basisrente_to_zero_limit(paar, legal)
    for path, v in changes.items():
        set_basisrente(paar, {int(path.split(".")[1]): v})
    r = run(paar, legal, extras=False)
    u = r.units[("", 2027)]
    assert changes["basisrente.2027"] > 0
    assert -150 <= u.v + u.pv <= 150  # at the Nullgrenze (rounded to 100 €)


def test_legacy_single_basisrente_is_migrated(personal, legal):
    personal.set_annahme("ui_m__basisrente", "12000.0")
    personal.set_annahme("ui_m__basisrente_year", "2027")
    s = from_personal(personal, legal)
    assert basisrente_by_year(s) == {2027: 12000.0}
