# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""All current inputs (Stellschrauben) as rows: label, value, origin, source in the XML."""

from __future__ import annotations

from dataclasses import fields
from datetime import date

from ..dates import fmt_date, fmt_eur, fmt_num, fmt_pct
from ..engine.settings import SECTIONS, Options, PersonSettings, gestaltungen
from ..io.personal_model import HERKUNFT_LABEL

PERSON_LABELS = {
    "salary_mode": "Gehaltseingabe (jahr = ganzjährig, real = tatsächlich gezahlt)", "birth": "Geburtsdatum", "steuerklasse": "Steuerklasse", "bz_jahre": "Betriebszugehörigkeit (Jahre)",
    "kfrist_monate": "Kündigungsfrist AG (Monate)",
    "vorbeschaeftigung_monate": "Versicherte Monate vor jetzigem AG", "end_date": "Austrittsdatum",
    "freistellung": "Freistellung", "freistellung_ab": "Freistellung ab", "vertragsschluss": "Kündigung/Aufhebungsvertrag am",
    "severance": "Abfindung (brutto)", "pay_idx": "Zahlungsmonat Abfindung", "fuenftel_ok": "Voraussetzungen Fünftelregelung",
    "rv_pflichtig": "RV-pflichtig", "sperrzeit_wochen": "Sperrzeit (Wochen)",
    "sperrzeit_ab_freistellung": "Sperrzeit ab Freistellung", "arbeitsuchend_datum": "Arbeitsuchendmeldung",
    "meldung": "Arbeitslosmeldung", "alg_monat": "ALG-Monatsbetrag",
    "urlaub_tage": "Urlaubsabgeltung (Tage)", "newjob": "Neue Beschäftigung", "newjob_start": "Beginn neue Beschäftigung",
    "newjob_salary": "Gehalt neue Beschäftigung", "kv_status": "KV-Status", "kv_beitrag_schaetzung": "Freiwilliger KV-Beitrag je Monat",
    "kv_sonstige_einnahmen": "Sonstige KV-pflichtige Einnahmen/Monat", "bonus": "Bonus", "bonus_year": "Bonus-Jahr",
    "werbungskosten": "Werbungskosten",
}
MEASURE_LABELS = {
    "betrag": "Betrag", "monat": "Monat", "gegenwert": "Gegenwert", "abziehbar": "Abziehbarer Anteil",
    "kaufpreis": "Kaufpreis", "gebaeudeanteil": "Gebäudeanteil", "nebenkosten_anteil": "Erwerbsnebenkosten",
    "afa_art": "AfA-Art", "darlehen": "Darlehen", "zins": "Zinssatz", "disagio_anteil": "Disagio",
    "zinsbindung_jahre": "Zinsbindung", "miete_jahr": "Kaltmiete/Jahr", "ortsuebliche_miete_jahr": "Ortsübliche Miete/Jahr",
    "bewirtschaftung_jahr": "Bewirtschaftung/Jahr", "kauf_erhaltung": "Instandsetzung nach Kauf",
}
OPTION_LABELS = {
    "lst_freibetrag": "LSt-Freibetrag (ELStAM)", "lst_freibetrag_year": "LSt-Freibetrag Jahr", "lst_antrag_datum": "LSt-Antrag am",
    "horizon_start": "Horizont Start", "horizon_end": "Horizont Ende", "gegenwert_arbeitszeit": "Gegenwert der Arbeitszeit",
    "church": "Kirchensteuer", "bundesland": "Bundesland", "kv_zusatz": "KV-Zusatzbeitrag",
    "kv_satz_allgemein": "KV allgemeiner Satz", "kv_abfindung_mode": "KV: Abfindung (1/2/3)",
    "kv_nachgehend_vorrang": "Nachgehender Anspruch vorrangig", "tarif_index": "Tarif-Fortschreibung p. a.",
    "ein_jahres_regel": "Ein-Jahres-Regel",
    "ein_jahres_ereignis": "Ereignis Ein-Jahres-Regel", "guenstiger_mode": "Günstigerprüfung",
    "bescheid_monat": "Bescheidmonat", 
    "sozialabgaben_anteil": "Sozialabgaben-Anteil", "rv_satz_annahme": "RV-Satz (Annahme)",
}
MONEY = {"salary", "rent", "capital", "childcare", "severance", "alg_monat", "newjob_salary", "kv_beitrag_schaetzung",
         "kv_sonstige_einnahmen", "bonus", "werbungskosten", "betrag", "kaufpreis", "darlehen",
         "miete_jahr", "ortsuebliche_miete_jahr", "bewirtschaftung_jahr", "kauf_erhaltung", "lst_freibetrag"}
SHARE = {"gebaeudeanteil", "nebenkosten_anteil", "zins", "disagio_anteil", "kv_zusatz", "tarif_index",
         "sozialabgaben_anteil", "rv_satz_annahme", "gegenwert_arbeitszeit", "gegenwert", "abziehbar"}


def fmt_path_value(path: str, v) -> str:
    """Format a settings value by its path (dict entries such as salary.2026 use the dict's name)."""
    parts = path.split(".")
    name = parts[-2] if parts[-1].lstrip("-").isdigit() and len(parts) > 1 else parts[-1]
    if v is None:
        return "–"
    return fmt_setting(name, v)


def fmt_children(children) -> str:
    return ", ".join(f"{gj}" + ("" if kg else " (ohne Kindergeld)") for gj, kg in children) or "keine"


def fmt_setting(name: str, v) -> str:
    if name == "children":
        return fmt_children(v)
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, date):
        return fmt_date(v)
    if name.endswith("_idx"):
        return f"{v % 12 + 1:02d}/{v // 12}"
    if name in MONEY:
        return fmt_eur(v)
    if name in SHARE:
        return fmt_pct(v, 2)
    if isinstance(v, float):
        return fmt_num(v, 3).rstrip("0").rstrip(",")
    return str(v)


def rows(s) -> list[tuple[str, list[tuple[str, str, str, str]]]]:
    """[(section, [(label, value, herkunft, xml path)])]"""
    out = []

    def row(path, label, name, v):
        herk = s.origin_of(path)
        return (label, fmt_setting(name, v), HERKUNFT_LABEL.get(herk, herk), s.xml_path_of(path))

    for i, ps in enumerate(s.persons):
        r = []
        for f in fields(PersonSettings):
            if f.name in ("id", "label", "rolle", "geplantes_ende", "alternativen", "freistellung", "freistellung_ab",
                          "sperrzeit_ab_freistellung", "urlaub_tage", "bonus", "bonus_year"):
                continue
            v = getattr(ps, f.name)
            if isinstance(v, dict):
                for y, val in sorted(v.items()):
                    lab = {"salary": "Bruttogehalt", "rent": "Einkünfte Vermietung", "capital": "Kapitalerträge"}[f.name]
                    r.append(row(f"persons.{i}.{f.name}.{y}", f"{lab} {y}", "severance", val))
                continue
            r.append(row(f"persons.{i}.{f.name}", PERSON_LABELS.get(f.name, f.name), f.name, v))
        title = ps.label + ("" if i == 0 or s.married else f" – nicht berücksichtigt (Familienstand {s.familienstand})")
        out.append((title, r))
    r = [(f"Bereich „{lab}“", "aktiv" if s.active(k) else "deaktiviert (nicht berücksichtigt)", "Planung", "")
         for k, lab in SECTIONS.items()]
    r += [("Familienstand", s.familienstand, "Angabe", "Haushalt/Familienstand"),
          ("Veranlagung", "Zusammenveranlagung" if s.joint else "Einzelveranlagung", "Angabe", "Haushalt/Veranlagungsart"),
         ("Kinder (Geburtsjahre)", fmt_children(s.children), "Angabe", "Haushalt/Kinder"),
          row("objekte_angeschafft_3j", "Mietobjekte in den letzten 3 Jahren angeschafft", "objekte_angeschafft_3j",
              s.objekte_angeschafft_3j)]
    for y, v in sorted(s.childcare.items()):
        r.append(row(f"childcare.{y}", f"Kinderbetreuungskosten {y}", "severance", v))
    for f in fields(Options):
        if f.name == "ein_jahres_ereignis":
            continue
        r.append(row(f"options.{f.name}", OPTION_LABELS.get(f.name, f.name), f.name, getattr(s.options, f.name)))
    out.append(("Haushalt und Optionen", r))
    r = []
    for gid, g in gestaltungen(s):
        base = f"measures.items.{gid}"
        names = g.params() + (["afa_art"] if g.typ == "kauf" else [])
        if g.typ == "sonstige":
            who = next((ps.label for ps in s.persons if ps.id == g.person), g.person)
            r.append((f"{g.label}: Person", who, "Angabe", s.xml_path_of(f"{base}.jahr")))
        r += [row(f"{base}.{n}", f"{g.label}: {MEASURE_LABELS.get(n, n)}", n, getattr(g, n)) for n in names]
    if not r:
        r.append(("Gestaltungen", "keine", "", ""))
    out.append(("Gestaltungen", r))
    return out
