Abfindungsoptimierer
====================

Planung von Abfindung, Austritt, Arbeitslosengeld und Krankenversicherung (Deutschland).
Dieses Programm ersetzt keine Steuer- oder Rechtsberatung. Alle Ergebnisse sind
Modellrechnungen auf Basis der eingelesenen Daten und vereinfachender Annahmen.

HAFTUNGSAUSSCHLUSS: siehe Hilfe -> Über ... bzw. README.md. Die Nutzung erfolgt auf eigene Verantwortung;
für Schäden aus der Nutzung ist die Haftung ausgeschlossen, soweit gesetzlich zulässig (Vorsatz, grobe
Fahrlässigkeit, Verletzung von Leben, Körper, Gesundheit und zwingende Vorschriften bleiben unberührt).

Starten
-------
Linux:    ./abfindungsoptimierer          (AppImage: Datei ausführbar machen und starten)
Windows:  abfindungsoptimierer.exe

Ohne Fenster (Ergebnis als JSON, optional PDF-Bericht):
Linux:    ./abfindungsoptimierer-cli persoenlich.xml recht.xml [--optimize] [--pdf bericht.pdf]
          (AppImage: ./Abfindungsoptimierer-<Version>-x86_64.AppImage --cli …)
Windows:  abfindungsoptimierer-cli.exe persoenlich.xml recht.xml …
Mit --help werden alle Optionen angezeigt, mit --version Version und Lizenz.

Beim ersten Start beginnt das Programm mit einer leeren Vorlage für die persönlichen
Daten und mit der Beispieldatei der rechtlichen Vorgaben (examples/ im Programmordner).
Die rechtlichen Werte der Beispieldatei vor einer Verwendung prüfen.
Einstellungen (zuletzt geöffnete Dateien, Dunkelmodus) liegen im Benutzerprofil.

Lizenz
------
Copyright (C) 2026 Lorenz Zhao

Dieses Programm ist freie Software unter der GNU General Public License, Version 3 oder
(nach Ihrer Wahl) jeder späteren Version, und wird OHNE JEDE GEWÄHRLEISTUNG bereitgestellt.
Quellcode: https://github.com/lorenzzhao/abfindungsoptimierer
Auf der Release-Seite jeder Version liegen neben diesem Paket der vollständige Quellcode
(abfindungsoptimierer-<Version>-source.tar.gz) und der Quellcode der enthaltenen
LGPL-Komponenten zum Download.

Das Programm enthält Komponenten Dritter, darunter Qt und Qt for Python (Copyright (C)
The Qt Company Ltd. und weitere Mitwirkende) unter der GNU Lesser General Public License
v3.0. Der Ordner "licenses" enthält die Lizenztexte und Hinweise aller Komponenten;
licenses/README.txt erklärt, was wo liegt, und licenses/SOURCES.txt nennt die Archive
mit ihren Prüfsummen.
