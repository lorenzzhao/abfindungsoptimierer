# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Dialog showing the prompt for checking the legal rules in an AI chat (copy or save)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QLabel, QMessageBox, QPlainTextEdit,
                               QVBoxLayout, QWidget)


class LegalPromptDialog(QDialog):
    def __init__(self, prompt: str, legal_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KI-Prompt: rechtliche Vorgaben prüfen")
        self.resize(900, 700)
        self.prompt = prompt
        self.legal_path = legal_path
        info = QLabel(
            "Diesen Text in einen KI-Chat kopieren. Er enthält die geladenen rechtlichen Vorgaben vollständig, das "
            "XML-Schema und die Jahre der Planung – <b>keine persönlichen Daten</b>. Die Antwort enthält eine geänderte "
            "XML-Datei: als eigene Datei speichern (die bisherige Datei nicht überschreiben), Änderungen prüfen und "
            "über <i>Datei → Rechtliche Vorgaben öffnen</i> laden – das Programm prüft sie dabei gegen das Schema. "
            "KI-Antworten können falsch sein; Werte mit amtlichen Quellen vergleichen.")
        info.setWordWrap(True)
        self.text = QPlainTextEdit(prompt)
        self.text.setReadOnly(True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        size = QLabel(f"<small>{len(prompt):,} Zeichen</small>".replace(",", "."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.copy_button = buttons.addButton("In Zwischenablage kopieren", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self.copy)
        self.save_button = buttons.addButton("Speichern unter …", QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button.clicked.connect(self.save)
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addWidget(self.text, 1)
        lay.addWidget(size)
        lay.addWidget(buttons)

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.prompt)
        self.copy_button.setText("Kopiert ✓")

    def save(self, path: str | None = None) -> bool:
        if not path:
            start = str(Path(self.legal_path).with_name("ki_prompt_rechtliche_vorgaben.md"))
            path, _ = QFileDialog.getSaveFileName(self, "Prompt speichern", start, "Markdown/Text (*.md *.txt)")
        if not path:
            return False
        try:
            Path(path).write_text(self.prompt, encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(e))
            return False
        return True
