# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Entry script of the standalone command-line program (PyInstaller)."""

import sys

from abfindung.cli import main

if __name__ == "__main__":
    sys.exit(main())
