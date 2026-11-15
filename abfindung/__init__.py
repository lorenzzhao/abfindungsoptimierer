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

HAFTUNG = (
    "Haftungsausschluss: Das Programm wird unentgeltlich und ohne Gewähr für Richtigkeit, Vollständigkeit und "
    "Aktualität bereitgestellt. Die Berechnungen sind vereinfachte Modelle; die rechtlichen Werte stammen aus einer "
    "ladbaren Datei und können veraltet oder fehlerhaft sein, ebenso die Programmlogik. Entscheidungen über "
    "Abfindung, Aufhebungsvertrag, Austrittstermin, Meldungen, Steuererklärung und Versicherung sind vor ihrer "
    "Umsetzung mit einer Steuerberatung bzw. Rechtsanwaltschaft, der Agentur für Arbeit und der Krankenkasse zu "
    "prüfen. Die Haftung der Urheberin bzw. des Urhebers für Schäden aus der Nutzung des Programms und seiner "
    "Ergebnisse ist ausgeschlossen, soweit gesetzlich zulässig. Unberührt bleibt die Haftung für Vorsatz und grobe "
    "Fahrlässigkeit, für Schäden aus der Verletzung von Leben, Körper oder Gesundheit und nach zwingenden "
    "gesetzlichen Vorschriften."
)
