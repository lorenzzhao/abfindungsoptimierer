# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Start the GUI: python -m abfindung [--personal X.xml] [--dark|--light]"""

from __future__ import annotations

import argparse
import os
import signal
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


def handle_ctrl_c(app, window) -> None:
    """Ctrl+C in the terminal closes the window like the close button (asks about unsaved changes); a second
    Ctrl+C quits at once without saving.

    Python only sees the signal while Python code runs; in Qt's event loop it would surface somewhere as a
    KeyboardInterrupt traceback and be lost. The handler only schedules the action, a timer lets Python run."""
    from PySide6.QtCore import QTimer

    state = {"pressed": False}

    def close() -> None:
        window.close()
        if window.isVisible():  # closing was cancelled in the save question
            state["pressed"] = False

    def on_sigint(_sig, _frame) -> None:
        if state["pressed"]:
            print("\nAbfindungsoptimierer: beendet ohne zu speichern.", file=sys.stderr)
            app.exit(130)
            return
        state["pressed"] = True
        print("\nAbfindungsoptimierer: wird geschlossen (erneut Strg+C: sofort beenden, ohne zu speichern).",
              file=sys.stderr)
        QTimer.singleShot(0, close)

    signal.signal(signal.SIGINT, on_sigint)
    tick = QTimer(app)
    tick.timeout.connect(lambda: None)  # gives Python the chance to run the handler
    tick.start(200)


def main(argv=None) -> int:
    from . import legal

    ap = argparse.ArgumentParser(description="Abfindungsoptimierer (grafische Oberfläche)",
                                 formatter_class=argparse.RawTextHelpFormatter)  # keeps the lines of --version
    ap.add_argument("--version", action="version", version=legal.version_text(ap.prog),
                    help="Version, Copyright und Lizenz anzeigen")
    ap.add_argument("--personal", "-p", help="persönliche Daten (XML)")
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
    w = MainWindow(a.personal, dark)
    w.show()
    handle_ctrl_c(app, w)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
