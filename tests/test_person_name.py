"""Optional names for the taxpayer and the spouse: shown instead of the role, saved in the XML."""

import pytest

from abfindung import charts
from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal, to_personal
from abfindung.io import load_personal
from abfindung.io.personal_writer import save_personal, to_bytes
from abfindung.report.inputs_table import rows


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_without_name_the_role_is_shown(s, personal):
    assert [p.label for p in s.persons] == ["Steuerpflichtige(r)", "Ehepartner"]
    assert [p.title for p in s.persons] == ["Steuerpflichtige(r)", "Ehepartner"]
    assert b' name="' not in to_bytes(to_personal(s, personal))


def test_name_replaces_role_in_results(s, legal):
    s.persons[0].name = "Erika"
    s.persons[1].name = "Max"
    assert s.persons[0].label == "Erika" and s.persons[0].title == "Erika (Steuerpflichtige(r))"
    r = run(s, legal)
    groups = {t.group for t in r.rs.values()}
    assert any(g and g.endswith("– Erika") for g in groups)
    assert not any("Steuerpflichtige(r)" in (t.label or "") for t in r.rs.values())
    from matplotlib.figure import Figure
    fig = Figure()
    charts.chart_gantt(fig, r, charts.LIGHT, None)
    assert {t.get_text() for t in fig.axes[0].get_yticklabels()} == {"Erika", "Max"}


def test_name_saved_and_loaded(personal, legal, tmp_path):
    s = from_personal(personal, legal)
    s.persons[1].name = "  Max  "
    out = save_personal(to_personal(s, personal), tmp_path / "p.xml")
    s2 = from_personal(load_personal(out), legal)
    assert [p.name for p in s2.persons] == ["", "Max"]
    assert s2.persons[1].label == "Max"
    assert s2.xml_path_of("persons.1.name").endswith("/@name")


def test_report_lists_name_only_when_given(s):
    s.persons[0].name = "Erika"
    secs = dict(rows(s))
    assert ("Name", "Erika") == secs["Erika (Steuerpflichtige(r))"][0][:2]
    assert not any(row[0] == "Name" for row in secs["Ehepartner"])
