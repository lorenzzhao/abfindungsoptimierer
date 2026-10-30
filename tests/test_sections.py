"""Optional input areas: disabled areas are kept in the XML but ignored by the calculation."""

import pytest

from abfindung.engine.optimizer import enumerate_discrete
from abfindung.engine.scenario import run
from abfindung.engine.settings import SECTIONS, from_personal, set_familienstand, to_personal
from abfindung.io import load_personal
from abfindung.io.personal_writer import save_personal

from .helpers import basisrente_by_year, set_basisrente


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_labels(s):
    assert [p.label for p in s.persons] == ["Steuerpflichtige(r)", "Ehepartner"]


def test_all_active_by_default(s):
    assert all(s.active(k) for k in SECTIONS)


def test_single_without_spouse(s, legal):
    set_familienstand(s, "ledig")
    r = run(s, legal)
    assert list(r.ctx.timelines) == ["P_Erika"]
    assert not any(k.startswith("alg_P_Max") for k in r.rs)
    assert all(k == "" for k, _ in r.units)  # single assessment only
    assert all("Ehepartner" not in c["_lab"] for c in enumerate_discrete(s, legal))
    assert len(s.persons) == 2 and not s.joint  # the spouse's data stays in the settings / file


def test_married_again_restores_joint_assessment(s, legal):
    set_familienstand(s, "geschieden")
    set_familienstand(s, "verheiratet")
    assert s.joint and len(run(s, legal, extras=False).ctx.timelines) == 2


def test_spouse_added_when_file_has_none(personal, legal, tmp_path):
    personal.persons = personal.persons[:1]
    keep = personal.persons[0].id
    personal.bescheide = []
    personal.vermietung.einkuenfte = [e for e in personal.vermietung.einkuenfte if e.person == keep]
    personal.kapital = [e for e in personal.kapital if e.person == keep]
    personal.household.familienstand = "ledig"
    personal.household.veranlagung = "Einzelveranlagung"
    s = from_personal(personal, legal)
    assert len(s.persons) == 1 and not s.married
    set_familienstand(s, "verheiratet")
    assert len(s.persons) == 2 and s.persons[1].label == "Ehepartner"
    run(s, legal, extras=False)
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")  # validated against the schema
    s2 = from_personal(load_personal(out), legal)
    assert s2.married and s2.joint and len(s2.persons) == 2


def test_household_disabled(s, legal):
    base = run(s, legal, extras=False)
    assert base.units[("", 2027)].kfb > 0
    s.sections["haushalt"] = False
    s.options.church = True
    r = run(s, legal, extras=False)
    units = [u for (k, y), u in r.units.items() if y == 2027]
    assert units and all(u.kfb == 0 and u.kist == 0 and u.kindergeld == 0 for u in units)


def test_kv_disabled(s, legal):
    s.sections["kv"] = False
    r = run(s, legal)
    assert sum(r.kv_by_year.values()) == 0
    assert not any(k.startswith("kv_") for k in r.rs)


def test_measures_disabled(s, legal):
    set_basisrente(s, {2027: 20_000})
    with_br = run(s, legal, extras=False).tax_by_year[2027]
    s.sections["gestaltungen"] = False
    without = run(s, legal, extras=False).tax_by_year[2027]
    assert without > with_br
    assert basisrente_by_year(s) == {2027: 20_000}


def test_options_disabled_uses_default_horizon(s, legal):
    s.options.horizon_end = 2031
    s.options.gegenwert_arbeitszeit = 1.0
    s.sections["optionen"] = False
    r = run(s, legal, extras=False)
    assert r.years == [2026, 2027, 2028]
    assert sum(r.salary_by_year.values()) > 0


def test_flags_roundtrip(s, personal, legal, tmp_path):
    s.sections["kv"] = False
    set_familienstand(s, "ledig")
    s.persons[0].birth = s.persons[0].birth.replace(year=1979)
    s.persons[1].steuerklasse = "III"
    s.objekte_angeschafft_3j = True
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")
    s2 = from_personal(load_personal(out), legal)
    assert not s2.active("kv") and s2.active("haushalt")
    assert s2.familienstand == "ledig" and not s2.joint and len(s2.persons) == 2
    assert s2.persons[0].birth.year == 1979 and s2.persons[1].steuerklasse == "III" and s2.objekte_angeschafft_3j
    # disabled values are still written and read
    assert s2.persons[1].severance == s.persons[1].severance


def test_salary_modes(s, legal):
    ps = s.persons[1]  # exit 28.02.2027, 80.000 per full year
    assert ps.employed_months(2026) == 12 and ps.employed_months(2028) == 0
    assert ps.employed_months(2027) == pytest.approx(2)
    assert ps.prorated(2027) == pytest.approx(80_000 * 2 / 12)
    before = run(s, legal, extras=False)
    from abfindung.engine.settings import set_salary_mode
    set_salary_mode(s, 1, "real", [2025, 2026, 2027, 2028])
    assert ps.salary_mode == "real" and ps.salary[2027] == pytest.approx(80_000 * 2 / 12, abs=0.01)
    assert 2028 not in ps.salary
    after = run(s, legal, extras=False)
    assert after.saldo == pytest.approx(before.saldo, abs=1)
    # a real amount for the exit year is spread over the months worked
    ps.salary[2027] = 20_000
    assert ps.annual_equiv(2027) == pytest.approx(120_000)
    assert run(s, legal, extras=False).ctx.timelines[ps.id].gross_in_year(2027)[0] == pytest.approx(20_000, abs=1)


def test_no_exit_keeps_the_employment(s, legal, personal, tmp_path):
    base = run(s, legal, extras=False)
    s.persons[1].austritt = False
    r = run(s, legal, extras=False)
    tl = r.ctx.timelines[s.persons[1].id]
    assert all(m.days["beschaeftigt"] for (y, _), m in tl.months.items() if y <= r.years[-1])
    assert tl.alg_end is None and sum(r.ctx.ae_gross[s.persons[1].id].values()) == 0
    assert sum(r.salary_by_year.values()) > sum(base.salary_by_year.values())
    assert all("P_Max" not in c.get("_lab", "") or "kein Austritt" in c["_lab"] for c in enumerate_discrete(s, legal))
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")
    assert from_personal(load_personal(out), legal).persons[1].austritt is False


def test_nobody_leaves(s, legal):
    for ps in s.persons:
        ps.austritt = False
    r = run(s, legal, extras=False)
    assert r.years[0] == s.stand.year and sum(r.alg_by_year.values()) == 0


def test_no_unemployment_benefit(s, legal, personal, tmp_path):
    base = run(s, legal, extras=False)
    s.persons[0].alg_aktiv = False
    r = run(s, legal, extras=False)
    pid = s.persons[0].id
    assert r.ctx.timelines[pid].alg_end is None
    assert sum(r.alg_by_year.values()) < sum(base.alg_by_year.values())
    assert sum(r.kv_by_year.values()) > sum(base.kv_by_year.values())  # no KV via the Agentur
    assert any("kein Arbeitslosengeld beantragt" in w for w, _ in r.warnings)
    assert all(f"persons.0.meldung" not in c for c in enumerate_discrete(s, legal))
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")
    assert from_personal(load_personal(out), legal).persons[0].alg_aktiv is False


def test_no_alg_removes_alg_everywhere(s, legal):
    from abfindung.engine.marginal import curves, knick

    for ps in s.persons:
        ps.alg_aktiv = False
    r = run(s, legal)
    assert all(u.pv == 0 for u in r.units.values())
    assert list(knick(r).lines) == ["ohne Abfindung", "mit Abfindung"] and curves(r).alg == 0
    alg = {k: t for k, t in r.rs.items() if t.group.startswith("ALG")}
    assert all(t.value in (0, 0.0) for k, t in alg.items() if not k.endswith("_fristende"))
    assert not any(k.endswith(("_dauer", "_sperrzeit", "_ruhen158")) for k in alg)
    assert not any("ALG ruht" in w for w, _ in r.warnings)
    assert "kein ALG" in " ".join(next(t for k, t in r.rs.items() if k.startswith("nullgrenze_")).steps)


def test_no_kv_for_a_person(s, legal):
    base = run(s, legal, extras=False)
    s.persons[1].kv_aktiv = False
    r = run(s, legal, extras=False)
    kv = r.ctx.kv[s.persons[1].id]
    assert not kv.months and sum(r.kv_by_year.values()) < sum(base.kv_by_year.values())
    assert r.ctx.kv[s.persons[0].id].months  # the other person is still calculated
    assert any("Krankenversicherung nicht berücksichtigt" in w for w, _ in r.warnings)
    assert not any(k.startswith(f"kv_{s.persons[1].id}_") or k == f"kv_abf_{s.persons[1].id}" for k in r.rs)
