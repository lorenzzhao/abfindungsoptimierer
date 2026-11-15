"""Prompt for an independent check of the whole calculation in an AI chat."""

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from abfindung.review_prompt import build_prompt  # noqa: E402

from .conftest import LEGAL, PERSONAL  # noqa: E402


@pytest.fixture(scope="module")
def window():
    from abfindung.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(str(PERSONAL), str(LEGAL), dark=False)
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def test_prompt_has_inputs_with_places_results_and_legal_rules(window):
    w = window
    rows = w.inputs.locations()
    p = build_prompt(w.res, w.legal, rows, today=date(2026, 11, 2))
    assert "Heutiges Datum: 02.11.2026" in p
    # every input field with its place in the program
    sev = next(i for i, r in enumerate(rows, 1) if r["path"] == "persons.0.severance")
    line = next(x for x in p.splitlines() if x.startswith(f"| E{sev} |"))
    assert "Eingaben › Steuerpflichtige(r) › " in line and "persons.0.severance" in line and "Abfindung/Betrag" in line
    assert len([x for x in p.splitlines() if x.startswith("| E")]) == len(rows)
    # every result, also the hidden ones, with meaning and the inputs it uses as E numbers
    w.results.toggles["liquiditaet"].setChecked(False)
    for t in w.res.rs.values():
        if not t.id.startswith("_"):
            assert f"### {t.id}: " in p
    kist = p.split("### kist_2027")[1].split("###")[0]
    assert "Ort: Ergebnisse › Steuer 2027 › Kirchensteuer 2027" in kist and "Bedeutung:" in kist
    assert ", E" in kist  # reference to the input row
    assert Path(LEGAL).read_text(encoding="utf-8").rstrip() in p
    assert "Ort im Programm" in p.split("## A. Eingaben")[0]  # the answer format asks for the place
    assert p.index("## Gewünschte Antwort") < p.index("## A. Eingaben") < p.index("## B. Ergebnisse") \
        < p.index("## C. Hinweise") < p.index("## D. Rechtliche Vorgaben")


def test_month_index_and_inactive_inputs(window):
    rows = window.inputs.locations()
    p = build_prompt(window.res, window.legal, rows)
    pay = next(x for x in p.splitlines() if "| persons.0.pay_idx |" in x)
    assert "/20" in pay.split("|")[3]  # month/year, not the internal index
    assert any(not r["active"] for r in rows)  # greyed out fields are marked


def test_dialog_warns_about_personal_data(window, tmp_path):
    from abfindung.gui.legal_prompt_dialog import ReviewPromptDialog

    d = ReviewPromptDialog("Prompt-Text", str(tmp_path))
    from PySide6.QtWidgets import QLabel

    assert any("persönlichen und finanziellen Daten" in lab.text() for lab in d.findChildren(QLabel))
    target = tmp_path / "x.md"
    assert d.save(str(target)) and target.read_text(encoding="utf-8") == "Prompt-Text"
    assert d.default_path.endswith("ki_prompt_gesamtpruefung.md")


def test_liability_disclaimer_is_shown():
    from abfindung import HAFTUNG
    assert "Haftung" in HAFTUNG and "soweit gesetzlich zulässig" in HAFTUNG and "grobe" in HAFTUNG
