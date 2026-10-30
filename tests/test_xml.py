from datetime import date
from pathlib import Path

import pytest

from abfindung.io import ValidationError, load_legal, load_personal
from abfindung.io.personal_writer import save_personal, to_bytes

from .conftest import LEGAL, PERSONAL


def test_load_legal(legal):
    assert 2026 in legal.tariffs
    assert legal.value("kap_abgeltung_satz") == 0.25
    assert legal.table("T_ALG_Anspruchsdauer").rows
    assert legal.rule("R_Fuenftel_Progressionsvorbehalt") is not None
    assert legal.source("Q_EStG").url


def test_param_carried_forward(legal):
    p = legal.param("est_grundfreibetrag", 2028)
    assert p.fortgeschrieben and p.year_used == 2026
    p = legal.param("est_grundfreibetrag", 2026)
    assert not p.fortgeschrieben
    # timeless parameter is never flagged
    assert not legal.param("kap_abgeltung_satz", 2030).fortgeschrieben
    t, fortg = legal.tariff(2027)
    assert fortg and t.year == 2026


def test_monat_tag_param(legal):
    assert legal.value("lst_erm_frist_ende") == (11, 30)


def test_load_personal(personal):
    assert len(personal.persons) == 2
    p = personal.person("P_Erika")
    assert p.geplantes_ende.value == date(2026, 12, 31)
    assert p.alg_monat.uncertain
    assert p.alternativen[0].freistellung_ab == date(2027, 1, 1)


def test_roundtrip(personal, tmp_path):
    personal.persons[0].abfindung.value = 123456.5
    personal.set_annahme("ui_test", "x")
    out = save_personal(personal, tmp_path / "p.xml")
    again = load_personal(out)
    assert again.persons[0].abfindung.value == 123456.5
    assert again.annahme("ui_test").value == "x"
    assert to_bytes(again) == to_bytes(personal)


def test_backup_on_save(personal, tmp_path):
    f = tmp_path / "p.xml"
    save_personal(personal, f)
    save_personal(personal, f)
    assert (tmp_path / "p.xml.bak").exists()


def test_invalid_export_rejected(personal):
    personal.persons[0].steuerklasse = "VII"
    with pytest.raises(ValidationError):
        to_bytes(personal)


def test_invalid_file(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text(PERSONAL.read_text(encoding="utf-8").replace("<Steuerklasse>IV", "<Steuerklasse>X"), encoding="utf-8")
    with pytest.raises(ValidationError) as ei:
        load_personal(bad)
    assert "Zeile" in ei.value.errors[0]
    with pytest.raises(ValidationError):
        load_legal(PERSONAL)  # wrong schema
    broken = tmp_path / "broken.xml"
    broken.write_text("<a>", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_legal(broken)


def test_old_file_with_variants_is_migrated(tmp_path):
    from abfindung.io import load_personal

    old = PERSONAL.read_text(encoding="utf-8").replace("<Planung>", """<Planung>
    <Abfindungsvarianten><Variante id="A"><Bezeichnung>x</Bezeichnung>
      <Zahlung person="P_Erika" monat="2027-01"/></Variante></Abfindungsvarianten>
    <ALGSzenarien><Szenario id="S1"><Bezeichnung>y</Bezeichnung>
      <Meldung person="P_Erika" datum="2027-01-01"/></Szenario></ALGSzenarien>""", 1)
    old = old.replace("</PersoenlicheDaten>", """<Referenzergebnisse><Hinweis>h</Hinweis>
    <Ergebnis id="r" beschreibung="Steuer 2027" einheit="EUR" variante="A">1</Ergebnis></Referenzergebnisse>
</PersoenlicheDaten>""")
    f = tmp_path / "alt.xml"
    f.write_text(old, encoding="utf-8")
    notes = load_personal(f).migration_notes
    assert len(notes) == 3 and all("nicht mehr unterstützt" in n for n in notes)


def test_source_address_matches_release_scripts():
    """The address shown in the program (About dialog, --version) is the release page the build refers to."""
    import json

    from abfindung import legal

    pins = json.loads((Path(LEGAL).parent.parent / "packaging" / "pins.json").read_text(encoding="utf-8"))
    assert legal.SOURCE_URL == pins["project_url"] and legal.SOURCE_URL in legal.version_text("x")
