import json
from datetime import date

import pytest

from abfindung import cli
from abfindung.engine.marginal import curves
from abfindung.engine.optimizer import enumerate_discrete, golden_section, optimize
from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal

from .conftest import LEGAL, PERSONAL


@pytest.fixture()
def s(personal, legal):
    return from_personal(personal, legal)


def test_golden_section_finds_maximum():
    x, fx = golden_section(lambda x: -(x - 12_300) ** 2, 0, 50_000, step=100)
    assert abs(x - 12_300) <= 100


def test_discrete_space(s):
    combos = enumerate_discrete(s)
    assert len(combos) > 10
    assert all("_lab" in c for c in combos)


def test_optimize_not_worse_than_current(s, legal):
    top, cur = optimize(s, legal, top_n=3)
    assert top and top[0].saldo >= cur.saldo - 1
    assert [c.saldo for c in top] == sorted((c.saldo for c in top), reverse=True)
    assert top[0].explanation


def test_payment_and_registration_defaults(s, legal):
    ps = s.persons[0]
    assert (ps.pay_year, ps.pay_month) == (2027, 1)  # month after the exit 31.12.2026
    assert ps.meldung == date(2027, 1, 1)
    assert s.origin_of("persons.0.pay_idx") == s.origin_of("persons.0.meldung") == "planung"


def test_curves_show_kink(s, legal):
    c = curves(run(s, legal, extras=False))
    assert c is not None and len(c.zve) == len(c.tax)
    ng = c.nullgrenze
    if ng > 1000:
        i_before = 1
        i_after = min(len(c.marginal) - 1, int(ng / 500) + 4)
        assert c.marginal[i_before] > c.marginal[i_after]


def test_cli_json(capsys):
    assert cli.main([str(PERSONAL), str(LEGAL), "--compact"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "saldo" in out and "2027" in out["jahre"]
    assert out["ergebnisse"]["saldo"]["wert"] == pytest.approx(out["saldo"])


def test_cli_validation_error(tmp_path, capsys):
    bad = tmp_path / "x.xml"
    bad.write_text("<x/>", encoding="utf-8")
    assert cli.main([str(bad), str(LEGAL)]) == 2


def test_pdf_export(s, legal, personal, tmp_path):
    from abfindung.report.pdf_export import export_pdf

    out = tmp_path / "bericht.pdf"
    export_pdf(str(out), run(s, legal), legal, focus_id="est_2027")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 50_000
