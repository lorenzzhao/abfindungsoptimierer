"""Origin (herkunft): chosen explicitly, kept on edit, written to the XML; optimiser only varies "planung"."""

import pytest

from abfindung.engine.optimizer import basisrente_to_zero_limit, enumerate_discrete, fixed_values
from abfindung.engine.settings import add_gestaltung, from_personal, is_planbar, to_personal
from abfindung.io import load_personal
from abfindung.io.personal_writer import save_personal

from .conftest import PERSONAL


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_bescheid_removed_and_migrated(tmp_path, legal):
    old = tmp_path / "alt.xml"
    old.write_text(PERSONAL.read_text(encoding="utf-8").replace('herkunft="angabe" jahr="2025"',
                                                                'herkunft="bescheid" jahr="2025"'), encoding="utf-8")
    pd = load_personal(old)
    assert pd.migration_notes
    assert pd.persons[0].gehalt(2025).herkunft == "angabe"


def test_edit_keeps_origin_and_save_writes_it(s, personal, legal, tmp_path):
    s.set("persons.0.severance", 170_000)
    assert s.origin_of("persons.0.severance") == "angabe"
    s.set_origin("persons.0.severance", "annahme")
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")
    s2 = from_personal(load_personal(out), legal)
    assert s2.persons[0].severance == 170_000 and s2.origin_of("persons.0.severance") == "annahme"


def test_planung_only_for_planbar_values(s):
    assert is_planbar("persons.0.pay_idx") and is_planbar("measures.items.G1.betrag")
    assert not is_planbar("persons.0.salary.2026") and not is_planbar("persons.0.bz_jahre")
    with pytest.raises(ValueError):
        s.set_origin("persons.0.salary.2026", "planung")


def test_optimizer_keeps_fixed_values(s, legal):
    s.set_origin("persons.0.pay_idx", "angabe")
    combos = enumerate_discrete(s, legal)
    assert all("persons.0.pay_idx" not in c for c in combos)
    assert any("persons.1.pay_idx" in c for c in combos)
    assert "Steuerpflichtige(r): Zahlungsmonat der Abfindung" in fixed_values(s, legal)


def test_basisrente_fixed_year_untouched(s, legal):
    gid = add_gestaltung(s, "basisrente", 2027, betrag=5_000)
    s.set_origin(f"measures.items.{gid}.betrag", "angabe")
    ch = basisrente_to_zero_limit(s, legal)
    assert "basisrente.2027" not in ch


def test_old_ui_planung_does_not_override_non_planbar_origin(personal, legal):
    personal.set_annahme("ui_P_Erika__sperrzeit_wochen", "12", herkunft="planung")
    personal.set_annahme("ui_P_Erika__pay_idx", str(2027 * 12), herkunft="planung")
    s = from_personal(personal, legal)
    assert s.origin_of("persons.0.sperrzeit_wochen") == "annahme"  # from SperrzeitErwartet in the XML
    assert s.origin_of("persons.0.pay_idx") == "planung"


def test_default_origins_and_removed_settings(personal, legal):
    from abfindung.engine.settings import default_origin

    assert default_origin("persons.0.pay_idx") == "planung"
    assert default_origin("persons.0.vorbeschaeftigung_monate") == "annahme"
    assert default_origin("options.tarif_index") == "annahme"
    assert default_origin("options.horizon_auto") == "angabe"
    personal.set_annahme("ui_P_Erika__bonus", "5000")
    s = from_personal(personal, legal)
    d = to_personal(s, personal)
    ids = {a.id for a in d.annahmen}
    assert "ui_P_Erika__bonus" not in ids and "ui_P_Erika__freistellung" not in ids
    assert not ids & {"ui_P_Erika__kfrist_aus_tabelle", "ui_P_Erika__alg_mode", "ui_o__kv_mode"}  # now the origin
    herk = {a.id: a.herkunft for a in d.annahmen}
    for aid in ("ui_P_Erika__salary_mode", "ui_o__horizon_auto", "ui_s__kv"):
        assert herk[aid] == "angabe", aid  # settings chosen by the user
    for aid in ("ui_P_Erika__vorbeschaeftigung_monate", "ui_P_Max__kv_sonstige_einnahmen", "ui_o__tarif_index"):
        assert herk[aid] == "annahme", aid  # genuine assumptions


def test_allowed_origins_per_value():
    from abfindung.engine.settings import allowed_origins

    assert allowed_origins("persons.0.end_date") == ("planung", "angabe", "annahme")
    assert allowed_origins("persons.0.salary.2026") == ("angabe", "annahme")
    assert allowed_origins("persons.0.alg_monat") == ("angabe", "annahme", "abgeleitet")
    assert "abgeleitet" in allowed_origins("persons.0.vertragsschluss")
    assert "illustrativ" in allowed_origins("measures.items.G1.kaufpreis")
    assert "illustrativ" not in allowed_origins("measures.items.G1.betrag")
    assert allowed_origins("measures.items.G1.gegenwert") == ("angabe", "annahme")
    assert allowed_origins("options.horizon_auto") == ("angabe",)


def test_set_origin_rejects_unsuitable(s):
    for path, h in (("persons.0.end_date", "illustrativ"), ("persons.0.salary.2026", "planung"),
                    ("options.horizon_auto", "annahme")):
        with pytest.raises(ValueError):
            s.set_origin(path, h)


def test_schema_rejects_unsuitable_origin(tmp_path):
    from abfindung.io import ValidationError

    bad = tmp_path / "bad.xml"
    bad.write_text(PERSONAL.read_text(encoding="utf-8").replace(
        '<GeplantesEnde herkunft="planung">', '<GeplantesEnde herkunft="abgeleitet">'), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_personal(bad)
