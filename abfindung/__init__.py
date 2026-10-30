# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Abfindungsoptimierer: planning and optimisation of severance pay, exit date,
unemployment benefit (ALG I) and health insurance under German law.

The calculation core lives in :mod:`abfindung.engine` and is UI-free.
All legal figures are read from the legal XML file; none are hard-coded.
"""

__version__ = "0.1.0"

DISCLAIMER = (
    "Dieses Tool ersetzt keine Steuer- oder Rechtsberatung. Alle Ergebnisse sind "
    "Modellrechnungen auf Basis der eingelesenen Daten und vereinfachender Annahmen."
)
