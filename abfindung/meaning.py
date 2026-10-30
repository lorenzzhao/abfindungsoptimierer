# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""What each result means, in plain language (shown above the calculation steps).

The texts are matched by the id of a result (see the ``tracer.new`` calls in the engine); the first matching
pattern wins. Every result id the engine produces must have a text (checked by the tests).
"""

from __future__ import annotations

import re

Y = r"\d{4}"

MEANINGS: list[tuple[str, str]] = [
    # -- overview -----------------------------------------------------------------------
    (r"^saldo$",
     "Die Zielgröße des Programms: wie viel Geld dem Haushalt im Planungshorizont netto zufließt, gezählt nur über "
     "die Posten, die von der Planung abhängen – ALG, Steuern, eigene Kranken- und Pflegeversicherungsbeiträge, "
     "Aufwand der Gestaltungen und Nettogehalt. Die Abfindung selbst ist bei jeder Einstellung gleich hoch und deshalb nicht "
     "enthalten; der Wert ist darum oft negativ. Aussagekräftig ist der Vergleich: Je höher der Saldo, desto besser "
     "die Einstellung."),
    (r"^steuer_gesamt$",
     "Die Summe aller Einkommensteuern, Solidaritätszuschläge und Kirchensteuern über alle Jahre des Horizonts. "
     "Sie zeigt, wie viel Steuer die aktuelle Planung insgesamt kostet; die Steuer ist meist der größte Posten, den "
     "Zahlungsjahr der Abfindung, Arbeitslosmeldung und Gestaltungen beeinflussen."),
    (r"^horizont$",
     "Die Kalenderjahre, über die gerechnet und verglichen wird. Alle Salden umfassen genau diese Jahre; "
     "Einstellungen lassen sich nur über denselben Horizont fair vergleichen."),
    (r"^gebunden$",
     "Der Teil der Ausgaben für Gestaltungen, der als Vermögen oder persönlicher Wert erhalten bleibt (zum Beispiel "
     "eine Basisrente, die bis zum Rentenbeginn gebunden ist). Er zählt nicht als Aufwand im Saldo, ist aber auch "
     "nicht frei verfügbar."),
    # -- Saldo per year -----------------------------------------------------------------
    (rf"^saldo_{Y}$",
     "Der Beitrag dieses Kalenderjahres zum Saldo: ALG minus Steuer minus eigene KV/PV-Beiträge minus Aufwand der "
     "Gestaltungen plus Gehalt im Saldo. Die Summe aller Jahre ergibt den Netto-Saldo."),
    (rf"^aufwand_{Y}$",
     "Was die Gestaltungen dieses Jahres den Haushalt kosten, ohne den Teil, der als Gegenwert erhalten bleibt. Die "
     "Steuerersparnis der Gestaltungen ist hier nicht abgezogen – sie steckt in der Steuer."),
    (rf"^gehalt_netto_{Y}$",
     "Das Gehalt dieses Jahres nach Sozialabgaben, soweit es in den Saldo eingeht (ohne den Gegenwert der "
     "Arbeitszeit). Die Steuer auf das Gehalt steckt in der Einkommensteuer. Wichtig, wenn das Austrittsdatum "
     "verändert wird: ein späterer Austritt bringt mehr Gehalt, aber oft mehr Steuer und weniger ALG."),
    # -- income tax per year / unit -----------------------------------------------------------
    (r"^steuer_.*\d{4}$",
     "Die gesamte Steuerlast dieses Jahres: Einkommensteuer, Solidaritätszuschlag und Kirchensteuer, bei "
     "Einzelveranlagung für beide Personen zusammen. Das ist der Betrag, den das Finanzamt für das Jahr am Ende "
     "festsetzt (ohne Abgeltungsteuer auf Kapitalerträge)."),
    (r"^veranlagung_",
     "Ob das Paar in diesem Jahr zusammen (Splitting) oder einzeln veranlagt wird. Bei „automatisch“ rechnet das "
     "Programm beide Arten und nimmt die günstigere; Einzelveranlagung kann sich lohnen, wenn eine Person eine "
     "Abfindung und die andere kaum Einkommen hat."),
    (r"^einkuenfte_",
     "Der Gesamtbetrag der Einkünfte: Arbeitslohn nach Werbungskosten, die Abfindung, Mieteinkünfte und die "
     "Ergebnisse der Gestaltungen (z. B. Erhaltungsaufwand, Immobilienkauf). Er ist der Ausgangspunkt der "
     "Steuerberechnung; ALG und Kapitalerträge gehören nicht dazu."),
    (r"^vorsorge_",
     "Die steuerlich abziehbaren Vorsorgeaufwendungen: Beiträge zur Kranken- und Pflegeversicherung sowie zur "
     "Altersvorsorge (gesetzliche Rente und Basisrente bis zum Höchstbetrag). Sie mindern das zu versteuernde "
     "Einkommen."),
    (r"^sa_",
     "Alle Sonderausgaben des Jahres: Vorsorgeaufwendungen, Kinderbetreuungskosten, Spenden (oder mindestens der "
     "Pauschbetrag). Sie werden vom Gesamtbetrag der Einkünfte abgezogen."),
    (r"^sonstige_",
     "Der abziehbare Teil der „Sonstigen Gestaltungen“ dieses Jahres. Er mindert das Einkommen der gewählten "
     "Person; die Abziehbarkeit ist eine eigene Angabe und wird nicht vom Programm geprüft."),
    (r"^pv_",
     "Das steuerfreie Arbeitslosengeld dieses Jahres. Es wird selbst nicht besteuert, erhöht aber den Steuersatz "
     "auf das übrige Einkommen (Progressionsvorbehalt) – deshalb kann ALG im Jahr der Abfindung teuer werden."),
    (r"^v_",
     "Das übrige zu versteuernde Einkommen ohne die Abfindung („v“). Es entscheidet zusammen mit dem ALG, wie stark "
     "die Fünftelregelung wirkt: Ist v klein oder negativ, wird die Abfindung besonders günstig besteuert."),
    (r"^zve_",
     "Das zu versteuernde Einkommen: übriges Einkommen v plus die außerordentlichen Einkünfte (Abfindung). Auf "
     "diesen Betrag wird der Steuertarif angewendet – bei einer Abfindung mit der Fünftelregelung."),
    (r"^est_",
     "Die Einkommensteuer des Jahres nach Tarif, mit Fünftelregelung für die Abfindung, Progressionsvorbehalt für "
     "das ALG und der Günstigerprüfung zwischen Kindergeld und Kinderfreibeträgen."),
    (r"^soli_",
     "Der Solidaritätszuschlag. Er fällt erst oberhalb einer Freigrenze an und steigt dann gleitend auf 5,5 % der "
     "Einkommensteuer."),
    (r"^kist_",
     "Die Kirchensteuer (8 oder 9 % der Einkommensteuer je nach Bundesland), falls Kirchensteuerpflicht besteht."),
    (r"^kap_",
     "Die Abgeltungsteuer auf Kapitalerträge. Sie wird an der Quelle einbehalten, hängt nicht von der Planung ab "
     "und geht deshalb nicht in den Saldo ein."),
    (r"^nullgrenze_",
     "Wie viel zusätzlicher Abzug (z. B. Basisrente, Erhaltungsaufwand) in diesem Jahr noch voll wirkt: bis das "
     "übrige zu versteuernde Einkommen (plus ALG) auf null sinkt. Bis dahin spart jeder abgezogene Euro im "
     "Abfindungsjahr oft mehr als einen Euro Steuer; darüber hinaus wirkt ein Abzug kaum noch."),
    (r"^sockel_",
     "Der Teil der Abfindung, der wegen der Fünftelregelung ganz steuerfrei bleibt, wenn das übrige Einkommen null "
     "oder negativ ist (bis zum Fünffachen des Grundfreibetrags). Er zeigt, wie viel Abfindung in einem Jahr ohne "
     "weitere Einkünfte steuerfrei wäre."),
    (r"^zusammenballung_",
     "Ob die Abfindung mit der günstigen Fünftelregelung besteuert wird. Voraussetzung ist eine Entschädigung, die "
     "zusammengeballt in einem Jahr zufließt und das sonst entgangene Einkommen übersteigt; fehlt das, wird die "
     "Abfindung voll mit dem normalen Tarif besteuert."),
    # -- unemployment benefit ------------------------------------------------------------------
    (r"^alg_.*_rate$",
     "Der monatliche Betrag des Arbeitslosengeldes (ALG I) dieser Person. Er hängt vom früheren Bruttogehalt, der "
     "Steuerklasse und den Kindern ab; die Abfindung mindert ihn nicht."),
    (r"^alg_.*_total$",
     "Das gesamte ALG dieser Person, das im Planungshorizont gezahlt wird. Es ist steuerfrei, wirkt aber über den "
     "Progressionsvorbehalt auf den Steuersatz."),
    (rf"^alg_.*_{Y}$",
     "Das ALG dieser Person in diesem Kalenderjahr. Wichtig für den Progressionsvorbehalt: ALG im Jahr der "
     "Abfindung erhöht deren Steuer."),
    (r"^tl_.*_fristende$",
     "Das Datum, zu dem das Arbeitsverhältnis bei ordentlicher Kündigung durch den Arbeitgeber frühestens hätte "
     "enden können. Endet es früher, ruht das ALG eine Zeit lang (§ 158 SGB III)."),
    (r"^tl_.*_ruhen158$",
     "Bis wann das ALG wegen der Abfindung ruht, weil die Kündigungsfrist nicht eingehalten wurde. In dieser Zeit "
     "wird kein ALG gezahlt; der Anspruch geht aber nicht verloren, er verschiebt sich."),
    (r"^tl_.*_sperrzeit$",
     "Bis wann eine Sperrzeit läuft, zum Beispiel nach einem Aufhebungsvertrag ohne wichtigen Grund. Während der "
     "Sperrzeit gibt es kein ALG, und die Anspruchsdauer wird gekürzt."),
    (r"^tl_.*_dauer$",
     "Wie viele Tage ALG dieser Person insgesamt zustehen, nach Versicherungszeit und Alter und abzüglich einer "
     "Minderung durch Sperrzeiten."),
    (r"^tl_.*_alg_start$",
     "Ab wann tatsächlich ALG gezahlt wird: nach der Arbeitslosmeldung und erst, wenn Sperrzeit und Ruhen vorbei "
     "sind."),
    # -- health insurance ----------------------------------------------------------------------
    (r"^kv_abf_",
     "Welche zusätzlichen Kranken- und Pflegeversicherungsbeiträge die Abfindung auslöst. Das betrifft nur Monate "
     "mit freiwilliger Versicherung; bei Pflichtversicherung und während ALG-Bezug ist die Abfindung beitragsfrei."),
    (rf"^kv_.*_{Y}$",
     "Die Kranken- und Pflegeversicherungsbeiträge, die diese Person in diesem Jahr selbst zahlt (freiwillig oder "
     "privat versichert). Zeiten mit Beschäftigung, ALG-Bezug oder Familienversicherung kosten keine eigenen "
     "Beiträge. Die Beiträge sind als Vorsorgeaufwand steuerlich abziehbar."),
    # -- derived inputs ---------------------------------------------------------------------------
    (r"^abl_.*_kfrist$",
     "Die gesetzliche Kündigungsfrist des Arbeitgebers, vom Programm aus der Betriebszugehörigkeit bestimmt. Sie "
     "entscheidet, ob das ALG wegen der Abfindung ruht."),
    (r"^abl_.*_kvstatus$",
     "Ob die Person vor dem Austritt pflicht- oder freiwillig versichert war, vom Programm aus dem Gehalt "
     "bestimmt. Davon hängt ab, ob und wie die Abfindung Krankenversicherungsbeiträge auslöst."),
    (r"^abl_.*_sperrzeit$",
     "Die vom Programm erwartete Sperrzeit: keine, wenn ein wichtiger Grund vorliegt (angemessene Abfindung und "
     "eingehaltene Kündigungsfrist), sonst die Regelsperrzeit. Die Agentur für Arbeit entscheidet im Einzelfall."),
    (r"^abl_.*_arbeitsuchend$",
     "Der späteste Tag, an dem sich die Person arbeitsuchend melden muss, ohne eine Sperrzeit wegen verspäteter "
     "Meldung zu riskieren."),
    (r"^abl_.*_kvbeitrag$",
     "Der vom Programm berechnete freiwillige Kranken- und Pflegeversicherungsbeitrag je Monat nach dem Austritt, "
     "aus den übrigen Einnahmen (ohne Abfindung)."),
    # -- liquidity ---------------------------------------------------------------------------------
    (r"^lst_abf_",
     "Die Lohnsteuer, die der Arbeitgeber bei der Auszahlung von der Abfindung einbehält. Sie ist nur eine "
     "Vorauszahlung: Die tatsächliche Steuer ergibt sich erst mit dem Steuerbescheid, die Differenz wird erstattet "
     "oder nachgezahlt."),
    (r"^lst_freibetrag$",
     "Ein auf der Lohnsteuerkarte (ELStAM) eingetragener Freibetrag. Er senkt nur den monatlichen Lohnsteuerabzug "
     "und verbessert so die Liquidität; die Jahressteuer ändert er nicht."),
    (r"^erstattung_",
     "Was nach dem Steuerbescheid für dieses Jahr erstattet (positiv) oder nachgezahlt (negativ) wird: die "
     "einbehaltene Lohnsteuer im Vergleich zur tatsächlichen Steuer. Wichtig für die Liquidität im Folgejahr."),
    (r"^liq_min$",
     "Der niedrigste Stand des kumulierten Kontostands im Liquiditätsplan. Er zeigt, ob zwischendurch Geld "
     "knapp wird, zum Beispiel vor einer Steuererstattung oder bei hohen Ausgaben für Gestaltungen."),
    # -- other -------------------------------------------------------------------------------------
    (r"^rv_",
     "Ein Überblick über die Beiträge zur gesetzlichen Rentenversicherung dieser Person (Beschäftigung, ALG). Nur "
     "zur Information: Er zeigt, wie sich Austritt und ALG auf die spätere Rente auswirken."),
    (r"^warn_\d+$",
     "Ein Hinweis aus der Berechnung, der für diese Planung wichtig sein kann – etwa ein Risiko, eine nicht "
     "erfüllte Voraussetzung oder eine Vereinfachung des Modells. Die genannten Regeln erklären den Hintergrund."),
]

_COMPILED = [(re.compile(p), text) for p, text in MEANINGS]


def meaning(result_id: str) -> str:
    """Plain-language meaning of a result (empty if none is known)."""
    for pattern, text in _COMPILED:
        if pattern.search(result_id):
            return text
    return ""
