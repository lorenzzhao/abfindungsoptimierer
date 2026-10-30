"""Gegenwert of measures: only (1 − share) × amount counts as expense in the Saldo."""

import pytest

from abfindung.engine.optimizer import _basisrente_tradeoff, basisrente_to_zero_limit
from abfindung.engine.scenario import run
from abfindung.engine.settings import add_gestaltung, default_origin, from_personal, to_personal
from abfindung.io import load_personal
from abfindung.io.personal_writer import save_personal


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_defaults_and_origin(s):
    gw = {typ: s.measures.items[add_gestaltung(s, typ, 2027)].gegenwert
          for typ in ("basisrente", "erhaltung", "spende", "kauf", "sonstige")}
    assert gw == {"basisrente": 1, "erhaltung": 1, "spende": 0, "kauf": 1, "sonstige": 0}
    assert default_origin("measures.items.G1.gegenwert") == "annahme"


def test_saldo_counts_only_part_without_gegenwert(s, legal):
    sp = add_gestaltung(s, "spende", 2027, betrag=1000)
    br = add_gestaltung(s, "basisrente", 2027, betrag=10_000)
    r = run(s, legal, extras=False)
    assert r.cost_by_year[2027] == pytest.approx(1000)  # donation 0 %, Basisrente 100 %
    assert r.gebunden == pytest.approx(10_000)
    s.measures.items[br].gegenwert = 0.6
    s.measures.items[sp].gegenwert = 0.5
    r2 = run(s, legal, extras=False)
    assert r2.cost_by_year[2027] == pytest.approx(500 + 4000)
    assert r2.gebunden == pytest.approx(500 + 6000)
    assert r2.saldo == pytest.approx(r.saldo - 3500)
    assert "Gegenwert" in " ".join(r2.rs["aufwand_2027"].steps)


def test_optimizer_weighs_basisrente_without_gegenwert(s, legal):
    ch = basisrente_to_zero_limit(s, legal)
    assert any(v > 0 for v in ch.values())
    for y in s.years():
        add_gestaltung(s, "basisrente", y, gegenwert=0.0)  # every euro is lost: the tax saving never outweighs it
    assert all(v == 0 for v in _basisrente_tradeoff(s, legal, ch).values())


def test_roundtrip(s, personal, legal, tmp_path):
    gid = add_gestaltung(s, "erhaltung", 2027, betrag=8000, gegenwert=0.3)
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")
    s2 = from_personal(load_personal(out), legal)
    assert s2.measures.items[gid].gegenwert == pytest.approx(0.3) and s2.measures.items[gid].betrag == 8000
    assert s2.origin_of(f"measures.items.{gid}.gegenwert") == "annahme"


def test_gegenwert_arbeitszeit(s, legal):
    r = run(s, legal, extras=False)
    net = sum(r.salary_by_year.values())
    assert net > 0 and s.origin_of("options.gegenwert_arbeitszeit") == "annahme"
    s.options.gegenwert_arbeitszeit = 0.25
    r2 = run(s, legal, extras=False)
    assert sum(r2.salary_by_year.values()) == pytest.approx(0.75 * net)
    assert r2.saldo == pytest.approx(r.saldo - 0.25 * net)
    assert r2.tax_by_year == r.tax_by_year  # the tax on the salary always counts in full


def test_former_salary_switch_migrates(personal, legal):
    personal.set_annahme("ui_o__include_salary", "false")
    s = from_personal(personal, legal)
    assert s.options.gegenwert_arbeitszeit == 1.0
    assert "ui_o__include_salary" not in {a.id for a in to_personal(s, personal).annahmen}
