# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Entry script of the standalone window program (PyInstaller)."""

import sys

from abfindung.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
