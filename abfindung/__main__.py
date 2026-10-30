# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Start the GUI: python -m abfindung [--personal X.xml] [--legal Y.xml] [--dark|--light]"""

from __future__ import annotations

import argparse
import os
import sys

# Qt's Wayland text input writes "Trying to disable … but 0x0 is focused" on every focus change (a harmless Qt
# message). Silenced here; rules the user sets in QT_LOGGING_RULES come later and take precedence.
QUIET_LOGGING = "qt.qpa.wayland.textinput=false"


def quiet_qt_logging() -> None:
    rules = os.environ.get("QT_LOGGING_RULES", "")
    if QUIET_LOGGING not in rules:
        os.environ["QT_LOGGING_RULES"] = ";".join(r for r in (QUIET_LOGGING, rules) if r)


def install_german_translation(app) -> bool:
    """German texts for Qt's own buttons and dialogs (Speichern, Abbrechen, Schließen, file dialogs)."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    translator = QTranslator(app)
    if translator.load("qtbase_de", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
        return True
    return False


def main(argv=None) -> int:
    from . import legal

    ap = argparse.ArgumentParser(description="Abfindungsoptimierer (grafische Oberfläche)",
                                 formatter_class=argparse.RawTextHelpFormatter)  # keeps the lines of --version
    ap.add_argument("--version", action="version", version=legal.version_text(ap.prog),
                    help="Version, Copyright und Lizenz anzeigen")
    ap.add_argument("--personal", "-p", help="persönliche Daten (XML)")
    ap.add_argument("--legal", "-r", help="rechtliche Vorgaben (XML)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dark", action="store_true", help="Dunkelmodus")
    g.add_argument("--light", action="store_true", help="Hellmodus")
    a = ap.parse_args(argv)

    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    quiet_qt_logging()  # before the QApplication reads the rules
    app = QApplication(sys.argv[:1])
    install_german_translation(app)
    app.setApplicationName("Abfindungsoptimierer")
    dark = True if a.dark else False if a.light else None
    w = MainWindow(a.personal, a.legal, dark)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
