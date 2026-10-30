# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""About dialog with version, copyright, licence, warranty disclaimer and source code note (the GPL's
"Appropriate Legal Notices"), Qt's copyright notice (LGPL-3.0, section 4c) and all licence texts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from .. import DISCLAIMER, legal


class LicensesDialog(QDialog):
    def __init__(self, documents: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lizenzen")
        self.resize(900, 600)
        self.documents = documents
        self.list = QListWidget()
        self.list.addItems([title for title, _ in documents])
        self.list.setMaximumWidth(280)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.list.currentRowChanged.connect(self._show)
        h = QHBoxLayout()
        h.addWidget(self.list)
        h.addWidget(self.view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(h, 1)
        lay.addWidget(buttons)
        if documents:
            self.list.setCurrentRow(0)

    def _show(self, row: int) -> None:
        if 0 <= row < len(self.documents):
            self.view.setPlainText(self.documents[row][1])


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Über {legal.APP_NAME}")
        self.setMinimumWidth(520)
        text = QLabel(
            f"<h3>{legal.APP_NAME} {legal.version()}</h3>"
            "<p>Planung von Abfindung, Austritt, Arbeitslosengeld und Krankenversicherung.</p>"
            f"<p>{DISCLAIMER}</p>"
            f"<p>{legal.COPYRIGHT}<br>Lizenz: <a href='{legal.LICENSE_URL}'>{legal.LICENSE_NAME}</a></p>"
            f"<p>{legal.NO_WARRANTY}</p><p>{legal.SOURCE_NOTE}</p>"
            f"<p>{legal.QT_COPYRIGHT}. Verwendet unter der <a href='{legal.LGPL_URL}'>GNU Lesser General Public "
            f"License v3.0</a>, die auf der <a href='{legal.GPL_URL}'>GNU General Public License v3.0</a> aufbaut.</p>"
            "<p>Weitere Komponenten: Python, Matplotlib, NumPy, Pillow, lxml, ReportLab und deren Abhängigkeiten. "
            "<i>Lizenzen …</i> zeigt alle Lizenztexte und Hinweise.</p>"
            "<p>Alle rechtlichen Werte stammen aus der geladenen XML-Datei. Keine Netzwerkzugriffe.</p>", self)
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setOpenExternalLinks(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        self.licenses_button = buttons.addButton("Lizenzen …", QDialogButtonBox.ButtonRole.ActionRole)
        self.documents = legal.license_documents()
        if self.documents:
            self.licenses_button.clicked.connect(lambda: LicensesDialog(self.documents, self).exec())
        else:
            self.licenses_button.setEnabled(False)
        lay = QVBoxLayout(self)
        lay.addWidget(text)
        lay.addWidget(buttons)
