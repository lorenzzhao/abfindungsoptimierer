"""Values the program derives itself when their origin is "abgeleitet" (engine/derive.py, alg_rate)."""

from datetime import date

import pytest

from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal, is_program_derived


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def derived(s, legal, path):
    s.set_origin(path, "abgeleitet")
    r = run(s, legal, extras=False)
    value, tid = r.ctx.derived[path]
    return value, r.rs[tid], r


def test_program_derived_paths():
    for f in ("fuenftel_ok", "kfrist_monate", "kv_status", "sperrzeit_wochen", "arbeitsuchend_datum",
              "kv_beitrag_schaetzung", "alg_monat"):
        assert is_program_derived(f"persons.1.{f}")
    assert not is_program_derived("persons.0.vertragsschluss")  # derived when loading, stays editable


def test_notice_period_from_table(s, legal):
    s.persons[0].bz_jahre = 10
    value, t, _ = derived(s, legal, "persons.0.kfrist_monate")
    assert value == 4 and "T_Kuendigungsfristen_AG" in t.steps[0]


def test_kv_status_from_salary(s, legal):
    vpg = legal.value("kv_versicherungspflichtgrenze", s.persons[1].end_date.year)
    s.persons[1].salary = {y: vpg + 1000 for y in s.persons[1].salary}
    assert derived(s, legal, "persons.1.kv_status")[0] == "freiwillig_gesetzlich"
    s.persons[1].salary = {y: vpg - 1000 for y in s.persons[1].salary}
    assert derived(s, legal, "persons.1.kv_status")[0] == "pflichtversichert"


def test_sperrzeit_wichtiger_grund(s, legal):
    ps = s.persons[0]
    ps.vertragsschluss = date(2026, 1, 1)  # notice period kept
    monat = ps.annual_equiv(ps.end_date.year) / 12
    ps.severance = 0.4 * monat * ps.bz_jahre
    assert derived(s, legal, "persons.0.sperrzeit_wochen")[0] == 0
    ps.severance = 0.8 * monat * ps.bz_jahre  # above the range
    assert derived(s, legal, "persons.0.sperrzeit_wochen")[0] == int(legal.value("alg_sperrzeit_arbeitsaufgabe_wochen"))
    ps.severance = 0.4 * monat * ps.bz_jahre
    ps.vertragsschluss = date(2026, 12, 1)  # notice period not kept
    assert derived(s, legal, "persons.0.sperrzeit_wochen")[0] > 0


def test_arbeitsuchend_latest_date_without_sperrzeit(s, legal):
    ps = s.persons[1]
    ps.vertragsschluss = date(2026, 1, 1)
    value, _, r = derived(s, legal, "persons.1.arbeitsuchend_datum")
    assert value == date(2026, 11, 28)  # end 28.02.2027 − 3 months
    assert not any("Arbeitsuchendmeldung" in w[0] for w in r.ctx.warnings)


def test_voluntary_kv_contribution(s, legal):
    s.set_origin("persons.1.kv_beitrag_schaetzung", "abgeleitet")
    s.persons[1].kv_beitrag_schaetzung = 9999  # ignored
    value, t, r = derived(s, legal, "persons.1.kv_beitrag_schaetzung")
    assert 0 < value < 2000 and "Mindestbemessung" in " ".join(t.steps)


def test_alg_amount_computed(s, legal):
    s.persons[0].alg_monat = 1.0  # ignored
    value, t, r = derived(s, legal, "persons.0.alg_monat")
    assert t.id == "alg_P_Erika_rate" and value == pytest.approx(t.value) and value > 1000


def test_former_switches_become_origin(personal, legal):
    personal.set_annahme("ui_P_Erika__kfrist_aus_tabelle", "true")
    personal.set_annahme("ui_P_Max__alg_mode", "berechnung")
    personal.set_annahme("ui_o__kv_mode", "berechnet")
    s = from_personal(personal, legal)
    assert s.origin_of("persons.0.kfrist_monate") == "abgeleitet"
    assert s.origin_of("persons.1.alg_monat") == "abgeleitet"
    assert s.origin_of("persons.0.alg_monat") != "abgeleitet"
    assert all(s.origin_of(f"persons.{i}.kv_beitrag_schaetzung") == "abgeleitet" for i in range(2))
