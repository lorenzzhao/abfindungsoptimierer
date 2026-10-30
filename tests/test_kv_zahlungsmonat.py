"""Ä4/Ä6: KV depending on the payment month; new employment."""

from datetime import date
from pathlib import Path

import pytest

from abfindung.dates import month_index
from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal
from abfindung.io import load_personal

FIXTURE = Path(__file__).parent / "fixtures" / "fiktiv_paar.xml"


@pytest.fixture()
def paar(legal):
    s = from_personal(load_personal(FIXTURE), legal)
    s.options.kv_abfindung_mode = 3  # spread over 12 months: the severance would be assessed
    return s


def _extra(r, pid):
    return r.rs[f"kv_abf_{pid}"].value


def test_payment_in_exit_month_compulsory_free(paar, legal):
    paar.persons[0].pay_idx = month_index(2027, 8)  # still employed in August (exit 31.8.)
    r = run(paar, legal, extras=False)
    assert _extra(r, "P1") == 0


def test_payment_while_employed_above_bbg_free(paar, legal):
    p2 = paar.persons[1]  # voluntarily insured
    p2.newjob, p2.newjob_start, p2.newjob_salary = True, date(2028, 1, 1), 90_000
    p2.pay_idx = month_index(2028, 6)
    r = run(paar, legal, extras=False)
    assert _extra(r, "P2") == 0


def test_payment_without_employment_costs(paar, legal):
    p1 = paar.persons[0]
    p1.pay_idx = month_index(2028, 1)
    p1.meldung = date(2029, 1, 2)      # no ALG before 2029: voluntary insurance after the follow-up cover
    r = run(paar, legal, extras=False)
    assert _extra(r, "P1") > 0


def test_new_job_before_registration_warns(paar, legal):
    p2 = paar.persons[1]
    p2.newjob, p2.newjob_start, p2.newjob_salary = True, date(2028, 1, 1), 80_000
    p2.meldung = date(2028, 4, 2)
    r = run(paar, legal, extras=False)
    assert any("vor der geplanten Arbeitslosmeldung" in w for w, _ in r.warnings)
    assert r.ctx.timelines["P2"].anspruch == 0


def test_optimizer_prefers_kv_cheapest_month(paar, legal):
    from abfindung.engine.optimizer import _best_months

    p1 = paar.persons[0]
    months = _best_months(paar, 0, legal, "aktuell", date(2029, 1, 2))
    assert months[0] == month_index(2027, 8)  # exit month: still employed -> no extra contribution
    assert [m // 12 for m in months] == [2027, 2028, 2029, 2030]
    assert p1.window()[0] <= min(months) and max(months) <= p1.window()[1]
