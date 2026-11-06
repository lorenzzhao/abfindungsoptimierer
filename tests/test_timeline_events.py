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
        ev = dict((k, d) for d, k in charts.timeline_events(ps, tl))
        assert ev["arbeitsuchend_frist"] == tl.meldefrist <= ps.end_date
        assert ev["arbeitslos_frist"] == ps.end_date + timedelta(days=1)
        assert ("arbeitslos_plan" in ev) == (ps.meldung != ps.end_date + timedelta(days=1))
    p2 = r.settings.persons[1]
    assert dict((k, d) for d, k in charts.timeline_events(p2, r.ctx.timelines[p2.id]))["arbeitslos_plan"] == date(2027, 3, 15)
    fig = Figure()
    charts.chart_gantt(fig, r, charts.LIGHT)
    labels = fig.axes[0].get_legend_handles_labels()[1]
    assert any("spätestens arbeitsuchend melden" in x for x in labels)
    assert any("spätestens arbeitslos melden" in x for x in labels)
    assert any("Arbeitslosmeldung (geplant" in x for x in labels)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert "15.03.27" in texts and r.ctx.timelines[p2.id].meldefrist.strftime("%d.%m.%y") in texts


def test_no_registration_dates_without_alg(s, legal):
    for ps in s.persons:
        ps.alg_aktiv = False
    r = run(s, legal)
    assert not any(charts.timeline_events(ps, r.ctx.timelines[ps.id]) for ps in r.settings.persons)
    fig = Figure()
    charts.chart_gantt(fig, r, charts.LIGHT)
    assert not any("melden" in x for x in fig.axes[0].get_legend_handles_labels()[1])
