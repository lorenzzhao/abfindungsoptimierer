"""Gestaltungen as a list of entries: several per kind and year, other Gestaltungen, migration of old files."""

import pytest

from abfindung.engine.scenario import run
from abfindung.engine.settings import add_gestaltung, from_personal, gestaltungen, remove_gestaltung, to_personal
from abfindung.io import load_personal
from abfindung.io.personal_writer import save_personal

from .conftest import PERSONAL


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_several_donations_in_one_year_add_up(s, legal):
    base = run(s, legal, extras=False)
    add_gestaltung(s, "spende", 2027, betrag=1000)
    add_gestaltung(s, "spende", 2027, betrag=500)
    r = run(s, legal, extras=False)
    assert r.cost_by_year[2027] == pytest.approx(1500)
    assert r.tax_by_year[2027] < base.tax_by_year[2027]


def test_other_gestaltung_reduces_income_of_the_person(s, legal):
    s.veranlagung[2027] = "einzel"
    base = run(s, legal, extras=False)
    gid = add_gestaltung(s, "sonstige", 2027, betrag=10_000, name="Fortbildung", person=s.persons[1].id)
    r = run(s, legal, extras=False)
    u_max = r.units[(f"{s.persons[1].id}_", 2027)]
    u_erika = r.units[(f"{s.persons[0].id}_", 2027)]
    assert u_max.sonstige == pytest.approx(10_000) and u_erika.sonstige == 0
    assert r.units[(f"{s.persons[1].id}_", 2027)].total < base.units[(f"{s.persons[1].id}_", 2027)].total
    s.measures.items[gid].abziehbar = 0.5
    assert run(s, legal, extras=False).units[(f"{s.persons[1].id}_", 2027)].sonstige == pytest.approx(5000)
    assert "Fortbildung 2027" in " ".join(r.rs[f"sonstige_{s.persons[1].id}_2027"].steps)


def test_two_purchases(s, legal):
    add_gestaltung(s, "kauf", 2027, kaufpreis=200_000, darlehen=150_000, miete_jahr=8000, gegenwert=0.0)
    one = run(s, legal, extras=False).cost_by_year[2027]
    add_gestaltung(s, "kauf", 2027, kaufpreis=200_000, darlehen=150_000, miete_jahr=8000, gegenwert=0.0)
    assert run(s, legal, extras=False).cost_by_year[2027] == pytest.approx(2 * one)


def test_roundtrip_all_kinds(s, personal, legal, tmp_path):
    ids = [add_gestaltung(s, "basisrente", 2027, betrag=5000, monat=6),
           add_gestaltung(s, "erhaltung", 2028, betrag=8000),
           add_gestaltung(s, "spende", 2027, betrag=300),
           add_gestaltung(s, "kauf", 2027, kaufpreis=250_000, afa_art="ab2023", zinsbindung_jahre=15),
           add_gestaltung(s, "sonstige", 2028, betrag=1200, name="Steuerberatung", person=s.persons[1].id, abziehbar=0.8)]
    s.set_origin(f"measures.items.{ids[0]}.betrag", "angabe")
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")  # validated against the schema
    s2 = from_personal(load_personal(out), legal)
    assert [(g.typ, g.jahr) for _, g in gestaltungen(s2)] == [(g.typ, g.jahr) for _, g in gestaltungen(s)]
    g = s2.measures.items
    assert g[ids[0]].monat == 6 and s2.origin_of(f"measures.items.{ids[0]}.betrag") == "angabe"
    assert g[ids[3]].afa_art == "ab2023" and g[ids[3]].zinsbindung_jahre == 15
    assert (g[ids[4]].name, g[ids[4]].person, g[ids[4]].abziehbar) == ("Steuerberatung", s.persons[1].id, 0.8)
    remove_gestaltung(s2, ids[1])
    assert ids[1] not in s2.measures.items


def test_old_tool_settings_become_entries(personal, legal):
    personal.set_annahme("ui_m__basisrente", "2027:9000.0;2028:0.0")
    personal.set_annahme("ui_m__erhaltung", "7000")
    personal.set_annahme("ui_m__erhaltung_year", "2028")
    personal.set_annahme("ui_m__gegenwert_erhaltung", "0.4")
    personal.set_annahme("ui_m__lst_freibetrag", "3000")
    s = from_personal(personal, legal)
    kinds = [(g.typ, g.jahr, g.betrag) for _, g in gestaltungen(s)]
    assert kinds == [("basisrente", 2027, 9000.0), ("erhaltung", 2028, 7000.0)]
    assert next(g for _, g in gestaltungen(s, "erhaltung")).gegenwert == pytest.approx(0.4)
    assert s.options.lst_freibetrag == 3000
    assert not [a for a in to_personal(s, personal).annahmen if a.id.startswith("ui_m__")]


def test_old_format_measures_are_dropped(tmp_path):
    old = PERSONAL.read_text(encoding="utf-8").replace("<Massnahmen>", """<Massnahmen>
      <Massnahme id="M_X" art="Basisrente" jahr="2027"><Bezeichnung>Kandidat</Bezeichnung>
        <Parameter name="kandidat_1" einheit="EUR" herkunft="illustrativ">10000</Parameter></Massnahme>""", 1)
    f = tmp_path / "alt.xml"
    f.write_text(old, encoding="utf-8")
    pd = load_personal(f)
    assert not pd.massnahmen and any("alten Format" in n for n in pd.migration_notes)
