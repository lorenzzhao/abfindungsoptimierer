# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Copyright, licence and source information shown to users.

The About dialog and the command line's ``--version`` use these texts, so users always see
the copyright, the licence, the lack of warranty and where the source code is (the GPL's
"Appropriate Legal Notices"), and Qt's copyright notice (LGPL-3.0, section 4c).
This module does not import Qt.
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

APP_NAME = "Abfindungsoptimierer"
COPYRIGHT = "Copyright (C) 2026 Lorenz Zhao"
LICENSE_NAME = "GNU General Public License, Version 3 oder neuer"
LICENSE_SPDX = "GPL-3.0-or-later"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
SOURCE_URL = "https://github.com/lorenzzhao/abfindungsoptimierer"
SOURCE_NOTE = ("Quellcode: " + SOURCE_URL + " – auf der Release-Seite jeder Version liegen neben den Programmpaketen "
               "der vollständige Quellcode (einschließlich der Build-Skripte) und der Quellcode der enthaltenen "
               "LGPL-Komponenten zum Download.")

QT_COPYRIGHT = "Qt und Qt for Python: Copyright (C) The Qt Company Ltd. und weitere Mitwirkende"
LGPL_URL = "https://www.gnu.org/licenses/lgpl-3.0.html"
GPL_URL = LICENSE_URL

NO_WARRANTY = ("Dieses Programm wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt. Es ist freie Software; Sie dürfen "
               "es unter den Bedingungen der Lizenz weitergeben und verändern.")

LICENSE_FILE = "LICENSE"
NOTICES_FILE = "THIRD_PARTY_NOTICES.txt"

_DISTRIBUTION = "abfindungsoptimierer"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    try:
        return metadata.version(_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        from . import __version__

        return __version__


def version_text(prog: str) -> str:
    """Text of ``--version``: version, copyright, licence, warranty, source code."""
    return (f"{prog} ({APP_NAME}) {version()}\n{COPYRIGHT}\n"
            f"Lizenz: {LICENSE_NAME} ({LICENSE_SPDX}), {LICENSE_URL}\n{NO_WARRANTY}\n{SOURCE_NOTE}\n"
            f"{QT_COPYRIGHT} (LGPL-3.0).")


def _folders() -> list[Path]:
    """Where licence files are: the "licenses" folder of a standalone package, else the source tree."""
    folders = []
    if getattr(sys, "frozen", False):
        folders.append(Path(sys.executable).resolve().parent / "licenses")
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller
    if bundle:
        folders.append(Path(bundle).parent / "licenses")
    folders.append(_REPO_ROOT)
    return folders


def read_text(name: str) -> str | None:
    for folder in _folders():
        try:
            return (folder / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return None


def license_documents() -> list[tuple[str, str]]:
    """(title, text) of the licence documents to show in the GUI: the program's licence, the overview of
    third-party components and, in a standalone package, every file of its "licenses" folder."""
    docs = []
    for title, name in (("Lizenz des Programms (GPL-3.0)", LICENSE_FILE),
                        ("Drittkomponenten (Übersicht)", NOTICES_FILE)):
        text = read_text(name)
        if text:
            docs.append((title, text))
    folder = next((f for f in _folders()[:2] if f.is_dir()), None) if getattr(sys, "frozen", False) else None
    if folder:
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder).as_posix()
            if path.is_file() and rel not in (LICENSE_FILE, NOTICES_FILE):
                try:
                    docs.append((rel, path.read_text(encoding="utf-8", errors="replace")))
                except OSError:
                    continue
    return docs
