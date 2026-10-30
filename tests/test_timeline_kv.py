"""ALG timeline and KV tests (synthetic example data)."""

from datetime import date, timedelta

import pytest

from abfindung.engine.alg import alg_rate
from abfindung.engine.health import build_kv
from abfindung.engine.settings import from_personal
from abfindung.engine.timeline import build_timeline
from abfindung.engine.trace import ResultSet, Tracer


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def run(s, legal, i=0):
    tr = Tracer(legal, s)
    rs = ResultSet()
    ps = s.persons[i]
    _, rate = alg_rate(ps, i, s, tr)
    tl = build_timeline(ps, i, s, tr, rs, rate, date(s.options.horizon_end + 3, 12, 31))
    return tl, tr, rs


def run_kv(s, legal, i=0):
    tl, tr, rs = run(s, legal, i)
    ps = s.persons[i]
    kv = build_kv(ps, i, s, tr, rs, tl, [(ps.pay_idx, ps.severance)], {ps.pay_year: ps.severance})
    return tl, kv


def test_example_defaults(s):
    erika = s.persons[0]
    assert erika.vertragsschluss == date(2026, 11, 30)  # derived from Freistellung until 31.3.2027
    assert erika.sperrzeit_wochen == 12


def test_ruhen_and_sperrzeit_parallel(s, legal):
    tl, _, _ = run(s, legal, 0)
    assert tl.ruhen158 and tl.ruhen158_end == date(2027, 3, 31)
    assert tl.sperr_end == date(2026, 12, 31) + timedelta(days=84)
    assert tl.alg_start == max(tl.ruhen158_end, tl.sperr_end) + timedelta(days=1)


def test_quarter_reduction_with_12_weeks(s, legal):
    tl, _, _ = run(s, legal, 0)
    assert tl.anspruch_tabelle == 360
    assert tl.minderung == 90  # max(84, 0.25 * 360)
    assert tl.anspruch == 270


def test_reduction_dropped_after_one_year(s, legal):
    s.persons[0].meldung = date(2028, 1, 2)
    tl, _, _ = run(s, legal, 0)
    assert tl.minderung_entfaellt and tl.anspruch == 360
    s.options.ein_jahres_regel = False
    tl, _, _ = run(s, legal, 0)
    assert tl.anspruch == 270


def test_no_ruhen_when_notice_kept(s, legal):
    tl, _, _ = run(s, legal, 1)
    assert not tl.ruhen158 and tl.ruhen158_end is None
    s.persons[0].freistellung = True
    s.persons[0].end_date = date(2027, 3, 31)
    tl, _, _ = run(s, legal, 0)
    assert not tl.ruhen158
    # Sperrzeit begins with the release from work
    assert tl.sperr_start == date(2027, 1, 1)


def test_anrechnung_share_age_and_tenure(s, legal):
    ps = s.persons[0]
    ps.bz_jahre = 3
    ps.birth = date(1995, 1, 1)
    assert run(s, legal, 0)[0].ruhen158_anteil == pytest.approx(0.60)
    ps.bz_jahre = 10
    ps.birth = date(1980, 5, 10)  # 46 at the end of employment
    assert run(s, legal, 0)[0].ruhen158_anteil == pytest.approx(0.60 - 0.10 - 0.10)
    ps.bz_jahre = 40
    ps.birth = date(1960, 1, 1)
    assert run(s, legal, 0)[0].ruhen158_anteil == pytest.approx(0.25)


def test_ruhen_ends_when_severance_consumed(s, legal):
    s.persons[0].severance = 5000  # small severance is used up quickly
    tl, _, _ = run(s, legal, 0)
    assert tl.ruhen158_end < tl.fristende


def test_alg_30_day_months(s, legal):
    tl, _, _ = run(s, legal, 0)
    rate = tl.rate_tag
    jun = tl.months[(2027, 6)]  # full month in ALG
    jul = tl.months[(2027, 7)]
    assert jun.alg == pytest.approx(30 * rate)
    assert jul.alg == pytest.approx(30 * rate)


def test_new_job_ends_alg_keeps_rest(s, legal):
    s.persons[0].newjob = True
    s.persons[0].newjob_start = date(2027, 6, 1)
    tl, _, _ = run(s, legal, 0)
    assert tl.days[date(2027, 6, 1)].status == "neue_beschaeftigung"
    assert tl.rest > 0


def test_late_jobseeker_registration(s, legal):
    s.persons[1].arbeitsuchend_datum = date(2027, 2, 1)
    tl, _, _ = run(s, legal, 1)
    assert tl.melde_end is not None and tl.warnings


# -- KV -----------------------------------------------------------------------------

def test_kv_compulsory_then_ruhen158_voluntary(s, legal):
    tl, kv = run_kv(s, legal, 0)
    jan = kv.months[(2027, 1)]
    assert jan.days["nachgehend"] == 31 and jan.own == 0
    feb = kv.months[(2027, 2)]
    assert feb.days["freiwillig"] == 28 and feb.own > 0
    may = kv.months[(2027, 5)]
    assert may.days["agentur"] == 31 and may.own == 0


def test_kv_voluntary_in_sperrzeit_first_month(s, legal):
    tl, kv = run_kv(s, legal, 1)  # Max: voluntarily insured, notice kept
    first = kv.months[(2027, 3)]
    assert first.days["freiwillig"] == 31 and first.own > 0
    later = kv.months[(2027, 4)]
    assert later.days["agentur"] == 30


def test_kv_compulsory_sperrzeit_first_month_follow_up(s, legal):
    s.persons[1].kv_status = "pflichtversichert"
    tl, kv = run_kv(s, legal, 1)
    assert kv.months[(2027, 3)].days["nachgehend"] == 31
    assert kv.months[(2027, 3)].own == 0


def test_kv_minimum_and_maximum_base(s, legal):
    s.set_origin("persons.0.kv_beitrag_schaetzung", "abgeleitet")  # computed from the income
    ps = s.persons[0]
    ps.capital = {2025: 0.0}
    ps.rent = {2025: 0.0}
    _, kv = run_kv(s, legal, 0)
    assert kv.months[(2027, 2)].base == pytest.approx(legal.value("kv_mindestbemessung_monat"))
    ps.kv_sonstige_einnahmen = 50_000
    _, kv = run_kv(s, legal, 0)
    assert kv.months[(2027, 2)].base == pytest.approx(legal.value("kv_bbg_monat"))


def test_kv_three_severance_options(s, legal):
    s.persons[0].capital = {2025: 0.0}
    s.persons[0].rent = {2025: 0.0}
    res = {}
    for mode in (1, 2, 3):
        s.options.kv_abfindung_mode = mode
        _, kv = run_kv(s, legal, 0)
        res[mode] = sum(kv.own_year(y) for y in s.years())
    assert res[1] < res[2]
    assert res[1] < res[3]


def test_kv_family_insurance(s, legal):
    ps = s.persons[1]
    ps.capital = {2025: 0.0}
    ps.rent = {2025: 0.0}
    ps.severance = 0
    s.persons[1].pay_idx = 2026 * 12  # no severance in later years
    tl, kv = run_kv(s, legal, 1)
    assert kv.months[(2027, 3)].days["familie"] == 31


def test_notice_period_derived_from_table_ignores_manual_value(s, legal):
    from abfindung.engine.scenario import run as run_scenario

    s.set_origin("persons.0.kfrist_monate", "abgeleitet")
    a = run_scenario(s, legal, extras=False).rs["tl_P_Erika_fristende"].value
    s.persons[0].kfrist_monate = 11
    r = run_scenario(s, legal, extras=False)
    assert r.rs["tl_P_Erika_fristende"].value == a
    assert "abl_P_Erika_kfrist" in r.rs["tl_P_Erika_fristende"].children
