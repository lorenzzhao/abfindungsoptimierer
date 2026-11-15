# Abfindungsoptimierer

Lokales Planungs- und Optimierungswerkzeug (Python, Qt/PySide6) für Abfindung, Austrittszeitpunkt,
Arbeitslosengeld (ALG I), Kranken-/Pflegeversicherung und steuerliche Gestaltungen in Deutschland –
für ein zusammenveranlagtes Ehepaar oder eine Einzelperson.

> **Dieses Tool ersetzt keine Steuer- oder Rechtsberatung.** Alle Ergebnisse sind Modellrechnungen.
> Die Nutzung erfolgt auf eigene Verantwortung; siehe [Haftungsausschluss](#haftungsausschluss).

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Benötigt Python ≥ 3.11 sowie PySide6, matplotlib, lxml und reportlab. Es gibt keine Netzwerkzugriffe und keine Telemetrie.

## Start (grafische Oberfläche)

```bash
.venv/bin/python -m abfindung --personal pfad/persoenliche_daten.xml --legal pfad/gesetzliche_vorgaben.xml
```

Ohne Parameter werden die zuletzt geöffneten Dateien geladen. Beim ersten Start beginnt das Programm mit einer
leeren Vorlage (*Datei → Neu*, `abfindung/resources/vorlage_persoenlich.xml`) und den rechtlichen Beispielwerten aus
`examples/`. Fiktive Beispiel-Personendaten liegen nur noch als Testdaten in `tests/fixtures/`.
`--dark` bzw. `--light` erzwingen das Farbschema (umschaltbar unter *Ansicht*).

Die Oberfläche hat drei Bereiche:

1. **Stellschrauben** (links): alle persönlichen Werte und Gestaltungen, die wichtigsten als Schieberegler
   (Gehalt je Jahr, Abfindungshöhe, Zahlungsmonat, Austrittsdatum, Meldedatum, ALG-Höhe, Basisrente …).
   Jeder Wert zeigt seine Herkunft (*Angabe, Annahme, abgeleitet, Planung …*); unsichere Werte sind
   orange markiert. Tooltips nennen Regel-IDs, Paragraphen und Quellen-Links. Der **Familienstand** (Tab
   „Steuerpflichtige(r)“) steuert den Tab „Ehepartner“: nur bei „verheiratet“ sichtbar und dann immer Teil der
   Berechnung; sonst Einzelveranlagung, die Daten des Ehepartners bleiben in der Datei. Kinder (Geburtsjahr,
   Kindergeld) werden im Tab „Haushalt“ gepflegt; Geburtsdatum und Steuerklasse je Person im Personen-Tab.
   Optional bekommt jede Person einen **Namen**; er steht dann statt „Steuerpflichtige(r)“ bzw.
   „Ehepartner“ in Ergebnissen, Hinweisen, Diagrammen und Bericht (Reiter: „Name (Rolle)“) und wird als
   Attribut `name` der Person in der XML-Datei gespeichert.
2. **Ergebnisse** (Mitte): alle berechneten Werte, gruppiert; ein Klick fokussiert genau einen Wert (▶, farbig
   hinterlegt). Schalter über der Liste blenden Bereiche aus, die nicht direkt in den Netto-Saldo eingehen
   (Steuer-Zwischenwerte, Liquidität, abgeleitete Termine, Hinweise) – nur Anzeige, gerechnet und optimiert wird
   immer mit allem; ein Verweis auf einen ausgeblendeten Wert blendet seinen Bereich wieder ein. Darunter drei Diagramme: Steuer & Knick (Gesamtsteuer über das zvE mit Nullgrenze und
   Grenzwirkung eines Abzugs), Zeitleiste (Gantt; über dem Balken die Fristen für die Arbeitsuchend- und die Arbeitslosmeldung und die
   geplanten Meldedaten, rot, wenn sie zu spät liegen; darunter Zahlungsmonat der Abfindung, Ende des
   Arbeitsverhältnisses, Freistellung, fiktives Ende der Kündigungsfrist, ALG-Beginn, letzter ALG-Tag, Erlöschen des
   Anspruchs und Beginn einer neuen Beschäftigung, jeweils mit Datum), Liquidität. Verschiedene Planungen vergleicht man
   durch Drehen an den Stellschrauben oder mit dem Optimierer. Ein Klick in ein Diagramm fokussiert den passenden Wert.
3. **Erklärung** (rechts): Rechenweg des fokussierten Werts mit eingesetzten Zahlen, verwendete Eingangsdaten
   (mit Herkunft und Fundstelle in der XML), rechtliche Parameter (Jahr, „fortgeschrieben“, Prüfstatus), Regeln mit
   Pseudoformel, Unsicherheit und Quellen. Links wechseln den Fokus.

Menü *Analyse → Optimieren* durchsucht Zahlungsmonate und Meldedaten vollständig und optimiert
Basisrente/Erhaltungsaufwand per goldenem Schnitt; die Top 5 werden mit Begründung angezeigt und lassen sich
übernehmen. *Datei → Speichern / Speichern unter* schreibt die aktuelle Planung als persönliche XML (vorher
XSD-Validierung, bei *Speichern* zusätzlich `.bak`-Sicherung). *Datei → PDF exportieren* erzeugt einen Bericht mit
allen Werten, Rechenwegen, Parametern, Regeln, Gesetzesverweisen und Quellen-Links zur unabhängigen Prüfung.

## Kommandozeile

```bash
.venv/bin/python -m abfindung.cli persoenliche_daten.xml gesetzliche_vorgaben.xml [--optimize] [--compact] [--pdf bericht.pdf]
```

Ausgabe als JSON: Saldo, Werte je Jahr, alle Ergebnisse mit Rechenweg, Warnungen, optional die Top 5 des
Optimierers.
Exit-Code 2 bei ungültigen Dateien.

## Eigenständiges Programm (Binary)

Linux (braucht Docker; baut in einem AlmaLinux-8-Container, läuft daher auch auf älteren Distributionen):

```bash
packaging/linux/build-in-docker.sh
```

Ergebnis in `release/`: `Abfindungsoptimierer-<Version>-x86_64.AppImage`, `abfindungsoptimierer-<Version>-linux-x86_64.tar.gz`,
das Quellcode-Archiv `abfindungsoptimierer-<Version>-source.tar.gz`, die Quellen der LGPL-/GPL-Komponenten in `release/sources/`
und `SHA256SUMS.txt` (siehe *Release*). Der Build verwendet ein festgelegtes Python (python-build-standalone) und festgelegte
Paketversionen (`packaging/pins.json`, `packaging/release-constraints.txt`), führt die Tests aus, sammelt mit
`packaging/collect_licenses.py` alle Lizenztexte in den Ordner `licenses` des Programms und bricht ab, wenn eine
Binärdatei keiner Komponente mit bekannter Lizenz zugeordnet werden kann.

Windows: `pwsh packaging/windows/build.ps1` (Python ≥ 3.11 und Inno Setup 6 nötig) – vorbereitet, aber noch nicht
getestet.

Nach einer Änderung am Icon (`abfindung/resources/app-icon.svg`): `QT_QPA_PLATFORM=offscreen python packaging/render_icons.py`.

## Release

Programm und Quellcode werden an derselben Stelle zum Download angeboten, der Release-Seite von
<https://github.com/lorenzzhao/abfindungsoptimierer>. Damit sind die Quellcode-Pflichten der GPL-3.0 (für das Programm)
und der LGPL (Qt, Qt for Python, libiconv, libquadmath, libfuse) sowie der GCC-Laufzeit erfüllt („gleichwertiger Zugang
an derselben Stelle“). Die Adresse steht in `abfindung/legal.py` (`SOURCE_URL`) und `packaging/pins.json`
(`project_url`); der Build bricht ab, wenn beide nicht übereinstimmen.

1. Version in `pyproject.toml` und `abfindung/__init__.py` setzen, committen, Tag anlegen und pushen:

   ```bash
   git tag -a v0.9.0 -m "Version 0.9.0"
   git push origin master v0.9.0
   ```

2. Aus dem sauberen Stand des Tags bauen: `packaging/linux/build-in-docker.sh` (Ergebnis in `release/`).
3. Eine GitHub-Release zum Tag anlegen und **alle** Dateien anhängen – die Pakete, das Quellcode-Archiv, die
   Versionsliste, `SHA256SUMS.txt` und jede Datei aus `release/sources/`:

   ```bash
   gh release create v0.9.0 --title "Abfindungsoptimierer 0.9.0" release/*.AppImage release/*.tar.gz release/*.txt release/sources/*
   ```

4. Die Quellarchive mindestens drei Jahre auf der Release-Seite lassen.

Die Pakete nur über die Release-Seite verteilen bzw. auf sie verlinken. Wer eine Paketdatei direkt weitergibt
(E-Mail, USB-Stick), muss die Quellen beilegen oder statt der Datei den Link zur Release-Seite weitergeben.
Aktualisierte Komponenten (`packaging/release-constraints.txt`, `packaging/pins.json`) immer zusammen mit ihren
Quellarchiven und Prüfsummen ändern; lxml und numpy sind an die Archive von libiconv bzw. GCC gebunden.

## Lizenz

Copyright (C) 2026 Lorenz Zhao. Freie Software unter der GNU General Public License, Version 3 oder neuer
(`LICENSE`), ohne jede Gewährleistung. Die verwendeten Komponenten Dritter und ihre Lizenzen beschreibt
`THIRD_PARTY_NOTICES.txt`; im Programm zeigt *Hilfe → Über … → Lizenzen …* alle Lizenztexte.

## Haftungsausschluss

Das Programm wird unentgeltlich und ohne Gewähr für Richtigkeit, Vollständigkeit und Aktualität bereitgestellt.
Es rechnet mit vereinfachten Modellen; die rechtlichen Werte (XML-Datei) und die Programmlogik können veraltet
oder fehlerhaft sein. Entscheidungen über Abfindung, Aufhebungsvertrag, Austrittstermin, Meldungen,
Steuererklärung und Versicherung sind vor ihrer Umsetzung mit einer Steuerberatung bzw. Rechtsanwaltschaft, der
Agentur für Arbeit und der Krankenkasse zu prüfen. Die Haftung der Urheberin bzw. des Urhebers für Schäden aus
der Nutzung des Programms und seiner Ergebnisse ist ausgeschlossen, soweit gesetzlich zulässig. Unberührt bleibt
die Haftung für Vorsatz und grobe Fahrlässigkeit, für Schäden aus der Verletzung von Leben, Körper oder
Gesundheit und nach zwingenden gesetzlichen Vorschriften. Es gelten zusätzlich die Haftungs- und
Gewährleistungsausschlüsse der GPL (§§ 15, 16).

## Tests

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

Die Tests verwenden ausschließlich die synthetischen Beispieldateien in `examples/`.

## Eingabedateien

| Datei | Schema | Namespace |
|---|---|---|
| Rechtliche Vorgaben | `abfindung/schemas/regulatory_input.xsd` | `urn:abfindung:recht:v1` |
| Persönliche Daten | `abfindung/schemas/personal_data.xsd` | `urn:abfindung:persoenlich:v1` |

Beide Dateien werden beim Laden gegen ihr Schema geprüft; Fehler werden mit Zeilennummer angezeigt.
**Alle rechtlichen Zahlen kommen ausschließlich aus der Datei der rechtlichen Vorgaben.** Fehlt ein Wert für ein Jahr,
wird der letzte verfügbare Wert verwendet und als „fortgeschrieben“ markiert (gilt auch für den Tarif; optional mit
Indexierung).

Die echten Dateien gehören nicht ins Repository (`.gitignore`). `examples/` enthält erfundene Beispielwerte.

Einstellungen ohne eigenes Schema-Element (Sperrzeit, KV-Option, neue Beschäftigung, Horizont, Rechtsfragen …) werden
beim Speichern als `Planung/Annahmen/Annahme id="ui_…"` abgelegt, ebenso Zahlungsmonat und Arbeitslosmeldung je Person.
Steuerbescheide, Abfindungsvarianten, ALG-Szenarien und Referenzergebnisse werden nicht mehr unterstützt; ältere Dateien werden beim
Laden ohne sie übernommen (Hinweis), beim Speichern entfallen sie.

### Optionale zusätzliche Parameter

Das Tool nutzt diese Parameter, wenn sie in den rechtlichen Vorgaben vorhanden sind (in der Beispieldatei enthalten):

- `rv_beitragssatz_gesamt` (Rentenversicherung, Anteil AN + AG; der ältere Name `rv_beitragssatz` wird weiter
  akzeptiert): nötig für die Kürzung des Basisrenten-Höchstbetrags um die gesetzlichen RV-Beiträge (R_Basisrente).
  **Fehlt er, wird mit dem Annahmewert aus den Optionen gerechnet (Standard 0 %) und eine Warnung angezeigt.**
- Für die Einzelveranlagung: `soli_freigrenze_einzeln`, `kap_sparer_pauschbetrag_einzeln`,
  `est_sonderausgaben_pauschbetrag_einzeln` (sonst Hälfte des Zusammenveranlagungswerts),
  `kind_freibetrag_saechlich_je_elternteil` + `kind_freibetrag_bea_je_elternteil`.
- `abf_auszahlung_spaetestens_monate_default` (Standard des Auszahlungsfensters).
- `alg_rahmenfrist_erweitert_monate` (5-Jahres-Frist für T_ALG_Anspruchsdauer, sonst 60 mit Hinweis).
- `rv_durchschnittsentgelt` (für Entgeltpunkte im Rentenausweis).

## Herkunft der Werte

Jeder Wert trägt eine Herkunft. Sie wird per Klick auf das Herkunfts-Badge festgelegt und beim Speichern so in die
XML geschrieben; das Verstellen eines Werts ändert sie nicht. Welche Herkunft wählbar ist, hängt von der Art des Werts
ab (im Schema als eigene Typen `HerkunftFaktTyp`, `HerkunftAbleitbarTyp`, `HerkunftPlanTyp` abgebildet):

| Art | erlaubt | Beispiele |
|---|---|---|
| Fakt | Angabe, Annahme | Gehälter, Betriebszugehörigkeit, Mieten, Kapitalerträge, Werbungskosten |
| ableitbar | Angabe, Annahme, abgeleitet | Kündigungsfrist, Fünftelregelung, KV-Status, ALG-Betrag, Sperrzeit, freiwilliger KV-Beitrag, Bundesland, Leistungssatz |
| planbar | Planung, Angabe, Annahme | Austrittsdatum, Abfindung, Zahlungsmonat, Meldung, Basisrente, Veranlagungsart |
| Einstellung | Angabe | Bedien-Schalter wie Gehaltseingabe-Modus, Horizont, Bereichs-Häkchen |

Datum der Kündigung/des Aufhebungsvertrags und Arbeitsuchendmeldung erlauben zusätzlich „abgeleitet“, die Parameter des Immobilienkaufs
zusätzlich „illustrativ“; freie Einträge (`Massnahme/Parameter`, `Annahme`) erlauben alle Werte inkl. „berechnet“.
„Annahme“ kennzeichnet unsichere Werte (Ergebnisse mit „≈“). **Der Optimierer verändert nur Werte mit Herkunft
„Planung“**; der Optimierer-Dialog listet die festen Werte. Frühere Herkünfte `bescheid` (beim Laden als `angabe`
übernommen) und `schaetzung` (in `annahme` aufgegangen) sind entfallen.

**„abgeleitet“ = das Programm bestimmt den Wert selbst** (Eingabefeld gesperrt, der Tooltip zeigt die Herleitung;
sonst gilt der eingetragene Wert):

| Wert | Herleitung |
|---|---|
| Voraussetzungen der Fünftelregelung | Entschädigung unterstellt, Zusammenballung geprüft |
| Kündigungsfrist des Arbeitgebers | Tabelle T_Kuendigungsfristen_AG nach Betriebszugehörigkeit |
| KV-Status | Jahresgehalt im Austrittsjahr gegen Versicherungspflichtgrenze (privat nur als Angabe) |
| Sperrzeit | wichtiger Grund: Abfindung 0,25–0,5 Monatsgehälter je Jahr und Kündigungsfrist eingehalten → keine, sonst Regelsperrzeit |
| Arbeitsuchendmeldung | spätester fristgerechter Tag (§ 38 SGB III) |
| Freiwilliger KV-Beitrag | Einnahmen zwischen Mindestbemessung und BBG × Beitragssatz (je Monat; angezeigt: erster Monat nach Austritt) |
| ALG-Monatsbetrag | eigene Berechnung aus dem Bemessungsentgelt (§§ 149 ff. SGB III) |

Die früheren Schalter „Kündigungsfrist aus Tabelle“, „ALG-Höhe“ und „Freiwilliger Beitrag“ sind entfallen; alte
Dateien werden beim Laden auf die Herkunft „abgeleitet“ umgestellt.

## Weitere Funktionen

- **Auszahlungsfenster** je Person (optionales XML-Element `Auszahlungsfenster`, im Tool als Häkchen unter
  „Abfindung“). Der Optimierer durchsucht jedes Jahr im Fenster und nimmt je Jahr den Monat mit dem geringsten
  KV-Mehrbeitrag (bei Gleichstand den frühesten). Zahlungen außerhalb des Fensters erzeugen eine Warnung (R_Faelligkeit).
- **Horizont automatisch** bis zum spätesten möglichen Zahlungsjahr bzw. Ende des ALG-Bezugs (unter „Optionen“
  abschaltbar). Der Optimierer vergleicht alle Kandidaten über einen gemeinsamen Horizont.
- **Zusammenballung bei Zahlung im Folgejahr** (R_Zusammenballung_Folgejahr): Vergleich mit dem Jahresgehalt des
  letzten vollen Jahres; sonst Warnung und Besteuerung ohne Fünftelregelung.
- **Veranlagungsart je Jahr** (automatisch/zusammen/einzel, XML-Element `Veranlagungswahl`); „automatisch“ rechnet
  beide Arten und nimmt die günstigere. Einzelveranlagung mit Grundtarif, Freibeträgen je Elternteil, halbem
  Kindergeld, Basisrente je Person, optional Sonderausgaben je zur Hälfte (§ 26a Abs. 2 EStG).
- **KV nach Zahlungsmonat:** Zahlung während einer Beschäftigung kostet keinen Mehrbeitrag; bei Verteilung zählen nur
  Monate mit freiwilliger Versicherung. Neuer Wert „KV-Mehrbeitrag durch die Abfindung“.
- **Neue Beschäftigung:** KV-Status im Rechenweg, Warnung bei Beginn vor der Arbeitslosmeldung.
- **Gestaltungen als Einträge** (Tab „Gestaltungen“): Basisrente, Erhaltungsaufwand, Spende, Immobilienkauf und
  „Sonstige Gestaltung“ (eigene Bezeichnung, Betrag, abziehbarer Anteil, Standard 100 %; mindert das Einkommen der
  gewählten Person). Jede Art mehrfach und je Jahr; je Eintrag Zahlungsmonat (Liquidität) und Gegenwert. Gespeichert
  als `Planung/Massnahmen/Massnahme` (immer mit Parameter `gegenwert`; Elemente im alten Format werden beim Laden
  entfernt). Bei der Basisrente zeigt der Eintrag die Nullgrenze des Jahres; der Optimierer schlägt je Jahr eine
  Basisrente bis zur Nullgrenze vor (gedeckelt durch den Höchstbetrag) und legt dafür bei Bedarf einen Eintrag an.
- **Kein Austritt** je Person (Haken „Scheidet aus“ im Personen-Tab): Die Beschäftigung läuft im ganzen Horizont
  weiter (Gehalt, Arbeitnehmeranteile KV/PV); Abfindung, ALG, Sperrzeit und neue Beschäftigung entfallen, die Werte
  bleiben gespeichert. Ohne jeden Austritt beginnt der Horizont mit dem Stand der Daten.
- **Kein Arbeitslosengeld** je Person (Haken „Arbeitslosengeld beantragen“ im Abschnitt „Arbeitslosengeld“): keine
  Meldung bei der Agentur, kein ALG, keine Sperrzeit; die KV nach dem Austritt richtet sich nach dem nachgehenden
  Anspruch, der Familienversicherung oder der freiwilligen Versicherung. Ohne ALG entfallen auch der
  Progressionsvorbehalt, die ALG-Linie im Knick-Diagramm und alle ALG-Einträge der Ergebnisliste.
- **Keine Krankenversicherung** je Person (Haken „Krankenversicherung berücksichtigen“ im Abschnitt
  „Krankenversicherung“): keine eigenen KV/PV-Beiträge, keine Arbeitnehmeranteile, keine KV/PV-Vorsorgeaufwendungen,
  kein KV-Mehrbeitrag durch die Abfindung. Der Bereich „KV“ (Tab) schaltet dasselbe für beide Personen.
- **KI-Prompt zur Prüfung der rechtlichen Vorgaben** (*Analyse → KI-Prompt …*): erzeugt einen Text für einen KI-Chat
  mit der geladenen Datei der rechtlichen Vorgaben (vollständig), dem XML-Schema, den Jahren der Planung, den von der
  Rechnung verwendeten und den ungeprüften Parametern sowie Regeln für eine schemakonforme Antwort (Änderungstabelle,
  vollständige geänderte XML-Datei). Enthält keine persönlichen Daten. Kopieren oder als Datei speichern; die
  Antwort als neue Datei speichern und über *Datei → Rechtliche Vorgaben öffnen* laden (XSD-Prüfung beim Laden).
- **KI-Prompt zur Prüfung der gesamten Berechnung** (*Analyse*): ein Text für eine unabhängige Prüfung durch eine KI
  mit allen Eingaben (je Feld der Ort im Programm „Reiter › Gruppe › Feld“, Einstellungs- und XML-Pfad, Herkunft,
  ob der Wert verwendet wird), allen Ergebnissen (Bedeutung, Rechenweg, verwendete Eingaben als E-Nummern,
  Parameter, Regeln), den Hinweisen und der Datei der rechtlichen Vorgaben. Die KI soll Befunde als Tabelle mit dem
  Ort im Programm liefern. **Enthält die persönlichen und finanziellen Daten** – der Dialog weist darauf hin.
- **Lohnsteuer-Freibetrag (ELStAM)** im Tab „Optionen“: wirkt nur auf den monatlichen Lohnsteuerabzug (Liquidität),
  nicht auf die Jahressteuer und den Saldo.
- **Knick-Diagramm** (Tab „Steuer & Knick“, unten): Mehrsteuer je zusätzlichem Euro über dem übrigen zvE mit drei
  Linien, Nullgrenzen mit/ohne ALG, aktueller Planung, Wertetabelle und Tooltip.
- **Steuerfreier Sockel der Fünftelregelung** je Jahr, **Gestaltungsrisiko-Hinweise** je Gestaltung
  (R_Gestaltungsrisiko), Warnung bei Abzügen über die Nullgrenze hinaus.
- Regressionstests mit dem fiktiven Datensatz `tests/fixtures/fiktiv_paar.xml` (Zahlungs- und Meldefälle, neue
  Beschäftigung, Veranlagungsarten, Basisrente bis zur Nullgrenze); `tests/fixtures/beispiel_persoenlich.xml` ist ein
  zweiter, einfacherer fiktiver Datensatz.

## Aufbau

```
abfindung/
  io/        XML-Lader, XSD-Validierung, Datenmodelle, Writer
  engine/    UI-freier Rechenkern (jede Funktion verweist auf ihre Regel-ID R_… und den Paragraphen)
    tariff.py       § 32a EStG aus den Tarifzonen, Splitting, Rundung
    fifth_rule.py   R_Fuenftel_Progressionsvorbehalt (BFH-Methode)
    timeline.py     Tageszeitleiste: Sperrzeit, Ruhen §§ 157/158, Anspruchsdauer, ALG-Bezug
    alg.py          ALG-Höhe (Angabe oder eigene Berechnung)
    derive.py       vom Programm abgeleitete Eingabewerte (Herkunft „abgeleitet“)
    health.py       KV/PV monatlich nach Status, freiwillige Beiträge, drei Optionen zur Abfindung
    income_tax.py   Jahressteuer je Veranlagung, Vermietung/Immobilienkauf, Vorsorge, Günstigerprüfung, Soli, KiSt
    liquidity.py    Lohnsteuerabzug auf die Abfindung, LSt-Freibetrag, monatliche Liquidität
    pension.py, marginal.py, optimizer.py, scenario.py, settings.py, trace.py
  gui/       Qt-Oberfläche (PySide6)
  report/    PDF-Export (reportlab)
  charts.py  Diagramme (GUI und PDF)
  explain.py Aufbereitung der Erklärungen (GUI und PDF)
```

Zielgröße (Saldo über den Horizont, Standard: Jahr des frühesten Austritts bis zwei Jahre danach):

```
Saldo = Σ ALG − Σ (ESt + Soli + KiSt) − Σ eigene KV/PV
        − Σ (1 − Gegenwert) × Betrag je Gestaltung
        + (1 − Gegenwert der Arbeitszeit) × Σ Gehalt abzgl. Sozialabgaben
```

Der **Gegenwert** (in %, Herkunft standardmäßig „Annahme“) ist der Teil, der als Vermögen oder persönlicher Wert
erhalten bleibt und deshalb nicht als Aufwand zählt; er wird je Eintrag festgelegt, Standard: Basisrente 100 %,
Erhaltungsaufwand 100 % (nur vorgezogen), Spenden 0 %, Sonstige Gestaltung 0 %, laufende Netto-Kosten eines Immobilienkaufs 100 % (Kaufpreis, Eigenkapital und Tilgung sind ohnehin
Umschichtung). Der **Gegenwert der Arbeitszeit** (Standard 0 %) bewertet freie Zeit im Verhältnis zum Nettogehalt –
wichtig, wenn das Austrittsdatum eine Stellschraube ist. Steuerwirkungen zählen immer voll. Die Abfindung selbst und
die Abgeltungsteuer sind konstant und nicht enthalten; aussagekräftig sind Unterschiede zwischen Einstellungen.

## Grenzen des Modells

- Lohnsteuer vereinfacht (Vorsorgepauschale über den Sozialabgaben-Anteil; Klassen V/VI angenähert). Sie wird nur
  für den Liquiditätsplan und die optionale ALG-Eigenberechnung verwendet. Die Einkommensteuer wird exakt nach Tarif
  berechnet.
- Keine Einkommensteuer-Vorauszahlungen im Liquiditätsplan; Kapitalertragsteuer gilt als an der Quelle abgegolten
  (Kirchensteuer-Kappung nicht modelliert).
- Kinder werden bis 18 Jahre berücksichtigt; KV-Beiträge ohne Kürzung um den Krankengeldanteil.
- Kalendermonat beim ALG mit 30 Tagen; Ruhen bei Urlaubsabgeltung über Kalendertage.
- Die Zuordnung der Abfindung bei freiwilliger KV ist kassenabhängig (Umschalter mit drei Optionen).
- Offene Rechtsfragen sind als Umschalter abgebildet (Ereignis der Ein-Jahres-Regel, nachgehender Anspruch vs.
  Anschlussversicherung, Günstigerprüfung mit § 34/§ 32b).
