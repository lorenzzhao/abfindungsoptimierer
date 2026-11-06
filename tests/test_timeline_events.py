"""Deadlines and planned dates in the timeline chart."""

from datetime import date, timedelta

import pytest
from matplotlib.figure import Figure

from abfindung import charts
from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_deadlines_for_registration(s, legal):
    s.persons[1].meldung = date(2027, 3, 15)  # planned after the first day of unemployment
    r = run(s, legal)
    for ps in r.settings.persons:
        tl = r.ctx.timelines[ps.id]
        ev = dict((k, d) for d, k in charts.timeline_events(ps, tl, r.ctx.payments[ps.id]))
        assert ev["arbeitsuchend_frist"] == tl.meldefrist <= ps.end_date
        assert ev["arbeitslos_frist"] == ps.end_date + timedelta(days=1)
        assert ("arbeitslos_plan" in ev) == (ps.meldung != ps.end_date + timedelta(days=1))
        assert ev["ende"] == ps.end_date and ev["alg_start"] == tl.alg_start and ev["erloeschen"] == tl.erloeschen
        assert ev["abfindung"] == date(ps.pay_idx // 12, ps.pay_idx % 12 + 1, 15)
        assert ("fristende" in ev) == (tl.ruhen158 and tl.fristende > tl.end)
    p2 = r.settings.persons[1]
    assert dict((k, d) for d, k in charts.timeline_events(p2, r.ctx.timelines[p2.id]))["arbeitslos_plan"] == date(2027, 3, 15)
    fig = Figure()
    charts.chart_gantt(fig, r, charts.LIGHT)
    labels = fig.axes[0].get_legend_handles_labels()[1]
    assert any("spätestens arbeitsuchend melden" in x for x in labels)
    assert any("spätestens arbeitslos melden" in x for x in labels)
    assert any("Arbeitslosmeldung geplant" in x for x in labels)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert "15.03.27" in texts and r.ctx.timelines[p2.id].meldefrist.strftime("%d.%m.%y") in texts


def test_no_registration_dates_without_alg(s, legal):
    for ps in s.persons:
        ps.alg_aktiv = False
    r = run(s, legal)
    for ps in r.settings.persons:  # exit and severance stay, nothing about ALG
        kinds = {k for _, k in charts.timeline_events(ps, r.ctx.timelines[ps.id], r.ctx.payments[ps.id])}
        assert kinds == {"ende", "abfindung"}
    fig = Figure()
    charts.chart_gantt(fig, r, charts.LIGHT)
    labels = fig.axes[0].get_legend_handles_labels()[1]
    assert not any("melden" in x or "ALG-" in x for x in labels) and "Ende Arbeitsverhältnis" in labels


def test_events_without_exit_and_with_new_job(s, legal):
    ps = s.persons[0]
    ps.austritt = False
    r = run(s, legal)
    p0 = r.settings.persons[0]
    assert charts.timeline_events(p0, r.ctx.timelines[p0.id], r.ctx.payments[p0.id]) == []
    s.persons[0].austritt = True
    s.persons[0].newjob = True
    s.persons[0].newjob_start = date(2028, 1, 1)
    r = run(s, legal)
    p0 = r.settings.persons[0]
    assert (date(2028, 1, 1), "newjob") in charts.timeline_events(p0, r.ctx.timelines[p0.id], r.ctx.payments[p0.id])


def test_gantt_rows_match_the_click_mapping(s, legal):
    """The chart panel maps a click to a person by y / ROW_GAP: the rows must lie on these positions."""
    r = run(s, legal)
    fig = Figure()
    charts.chart_gantt(fig, r, charts.LIGHT)
    n = len(r.settings.persons)
    assert list(fig.axes[0].get_yticks()) == [charts.ROW_GAP * i for i in range(n)]
    assert [t.get_text() for t in fig.axes[0].get_yticklabels()] == [p.label for p in reversed(r.settings.persons)]
