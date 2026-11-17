"""Prompt for checking the legal rules in an AI chat."""

from datetime import date
from pathlib import Path

from abfindung.engine.scenario import run
from abfindung.engine.settings import from_personal
from abfindung.io.xml_loader import LEGAL_XSD
from abfindung.legal_prompt import build_prompt

from .conftest import LEGAL


def test_prompt_contains_file_schema_years_and_used_parameters(legal, personal):
    r = run(from_personal(personal, legal), legal, extras=False)
    used = sorted({k.split("@")[0] for k in r.tracer.used_params})
    p = build_prompt(legal, r.years, used, today=date(2026, 11, 2))
    assert Path(LEGAL).read_text(encoding="utf-8").rstrip() in p  # the file exactly as loaded
    assert LEGAL_XSD.read_text(encoding="utf-8").rstrip() in p
    assert "Heutiges Datum: 02.11.2026" in p and f"Jahren {r.years[0]}–{r.years[-1]}" in p
    assert "est_grundfreibetrag" in p.split("## Aktuelle Datei")[0]  # listed among the parameters used
    assert "geprueft=\"false\"" in p and "vollständige geänderte XML-Datei" in p
    assert p.index("## Gewünschte Antwort") < p.index("## Aktuelle Datei") < p.index("## XML-Schema")


def test_prompt_has_no_personal_data(legal, personal):
    s = from_personal(personal, legal)
    r = run(s, legal, extras=False)
    p = build_prompt(legal, r.years, [])
    for ps in s.persons:
        assert ps.id not in p
    assert "Erika" not in p and "persoenlich" not in p.lower().replace("persönliche daten", "")


def test_dialog_copy_and_save(tmp_path):
    import os
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    from PySide6.QtWidgets import QApplication

    from abfindung.gui.legal_prompt_dialog import LegalPromptDialog

    app = QApplication.instance() or QApplication([])
    d = LegalPromptDialog("Prompt-Text", str(tmp_path))
    d.copy()
    assert app.clipboard().text() == "Prompt-Text"
    target = tmp_path / "prompt.md"
    assert d.save(str(target)) and target.read_text(encoding="utf-8") == "Prompt-Text"
    d.close()
