# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""PDF report with all current values, calculation steps, legal parameters, rules and
sources – structured so that it can be checked independently (also with AI tools)."""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from .. import DISCLAIMER, HAFTUNG, __version__, charts, explain
from ..dates import fmt_eur, fmt_month
from ..engine.marginal import curves, knick
from .inputs_table import rows as input_rows

FONT = "DejaVuSans"
FONT_B = "DejaVuSans-Bold"


def _register_fonts() -> None:
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont(FONT, str(base / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_B, str(base / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSansMono", str(base / "DejaVuSansMono.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily(FONT, normal=FONT, bold=FONT_B, italic=FONT, boldItalic=FONT_B)


def _styles():
    ss = getSampleStyleSheet()
    st = {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName=FONT_B, fontSize=20, leading=24),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName=FONT_B, fontSize=15, leading=19, spaceBefore=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName=FONT_B, fontSize=12, leading=15, spaceBefore=8),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName=FONT_B, fontSize=10, leading=13, spaceBefore=6,
                             spaceAfter=2),
        "body": ParagraphStyle("b", parent=ss["BodyText"], fontName=FONT, fontSize=8.5, leading=11, alignment=TA_LEFT),
        "small": ParagraphStyle("s", parent=ss["BodyText"], fontName=FONT, fontSize=7.2, leading=9),
        "cell": ParagraphStyle("c", parent=ss["BodyText"], fontName=FONT, fontSize=7, leading=8.6),
        "cellb": ParagraphStyle("cb", parent=ss["BodyText"], fontName=FONT_B, fontSize=7, leading=8.6),
        "mono": ParagraphStyle("m", parent=ss["Code"], fontName="DejaVuSansMono", fontSize=7, leading=8.6),
        "warn": ParagraphStyle("w", parent=ss["BodyText"], fontName=FONT, fontSize=8.5, leading=11,
                               textColor=colors.HexColor("#9a4b00")),
        "big": ParagraphStyle("big", parent=ss["BodyText"], fontName=FONT_B, fontSize=14, leading=18,
                              textColor=colors.HexColor("#0b5cad")),
    }
    return st


class _Doc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "_toc_level", None) is not None:
            text = flowable.getPlainText()
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=flowable._toc_level, closed=flowable._toc_level > 0)
            self.notify("TOCEntry", (flowable._toc_level, text, self.page, key))


def _h(text: str, style, level: int) -> Paragraph:
    p = Paragraph(escape(text), style)
    p._toc_level = level
    return p


def _p(text: str, style) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _table(data, col_widths, st, header=True, zebra=True) -> Table:
    cells = []
    for i, row in enumerate(data):
        cells.append([c if not isinstance(c, str) else Paragraph(escape(c), st["cellb"] if (header and i == 0) else st["cell"])
                      for c in row])
    t = Table(cells, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3ecf6")))
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f7f7f7")))
    t.setStyle(TableStyle(style))
    return t


def _fig_image(draw, width_mm=175, height_mm=100) -> Image:
    fig = Figure(figsize=(width_mm / 25.4, height_mm / 25.4), dpi=150)
    draw(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    buf.seek(0)
    return Image(buf, width=width_mm * mm, height=height_mm * mm)


def export_pdf(path: str, res, legal, focus_id: str | None = None, optimizer_top=None, personal_path: str | None = None) -> str:
    _register_fonts()
    st = _styles()
    s = res.settings
    W = 180 * mm
    now = datetime.now()
    story = []

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 6.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(15 * mm, 9 * mm, DISCLAIMER[:150])
        canvas.drawString(15 * mm, 6 * mm, f"Abfindungsoptimierer {__version__} · erstellt {now:%d.%m.%Y %H:%M} · "
                                           f"Horizont {s.options.horizon_start}–{s.options.horizon_end}")
        canvas.drawRightString(A4[0] - 15 * mm, 6 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    # -- title ---------------------------------------------------------------------
    story.append(_p("Abfindungsoptimierer – Bericht", st["title"]))
    story.append(_p(f"Erstellt am {now:%d.%m.%Y um %H:%M}", st["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Wichtiger Hinweis:</b> {escape(DISCLAIMER)} Alle Gesetzeswerte stammen aus der "
                           "eingelesenen Datei der rechtlichen Vorgaben; Parameter mit dem Status „ungeprüft“ oder "
                           "„fortgeschrieben“ sowie persönliche Werte mit der Herkunft „Annahme“ sind "
                           "besonders zu prüfen.", st["warn"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_p(escape(HAFTUNG), st["small"]))
    story.append(Spacer(1, 4 * mm))
    meta = [["Datei", "Inhalt"],
            ["Persönliche Daten", f"{Path(personal_path).name if personal_path else '–'} (gegen personal_data.xsd validiert)"],
            ["Rechtliche Vorgaben", f"mit dem Programm ausgeliefert ({Path(legal.path).name}) – Stand {legal.stand}; "
                                    f"{legal.rechtsstand} (gegen regulatory_input.xsd validiert)"]]
    story.append(_table(meta, [45 * mm, W - 45 * mm], st))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(f"Netto-Saldo {s.options.horizon_start}–{s.options.horizon_end}: {escape(fmt_eur(res.saldo))}",
                           st["big"]))
    yr = [["Jahr", "ALG", "Steuer (ESt+Soli+KiSt)", "eigene KV/PV", "Aufwand Gestaltungen", "Gehalt im Saldo", "Saldo"]]
    for y in res.years:
        yr.append([str(y), fmt_eur(res.alg_by_year[y]), fmt_eur(res.tax_by_year[y]), fmt_eur(res.kv_by_year[y]),
                   fmt_eur(res.cost_by_year[y]), fmt_eur(res.salary_by_year[y]),
                   fmt_eur(res.saldo_by_year[y])])
    story.append(_table(yr, [18 * mm] + [27 * mm] * 6, st))
    story.append(Spacer(1, 2 * mm))
    story.append(_p(f"Gegenwert der Gestaltungen (nicht im Saldo): {fmt_eur(res.gebunden)} · Liquiditätstiefpunkt "
                    f"{fmt_eur(res.liq_min)}" + (f" im {fmt_month(*res.liq_min_month)}" if res.liq_min_month else ""),
                    st["body"]))
    story.append(_p("Saldo = Σ ALG − Σ Steuer − Σ eigene KV/PV − Σ Aufwand der Gestaltungen ohne Gegenwert"
                    + " + Σ Gehalt abzgl. Sozialabgaben ohne Gegenwert der Arbeitszeit"
                    + ". Die Abfindung selbst und die Abgeltungsteuer sind konstant und nicht enthalten.", st["small"]))
    if focus_id and focus_id in res.rs:
        t = res.rs[focus_id]
        story.append(Spacer(1, 2 * mm))
        story.append(_p(f"Zum Zeitpunkt des Exports fokussiert: {t.label} = {t.fmt()} (Rechenweg in Abschnitt 5)", st["body"]))

    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("toc0", fontName=FONT_B, fontSize=9, leading=12, leftIndent=0),
                       ParagraphStyle("toc1", fontName=FONT, fontSize=8, leading=10, leftIndent=10)]
    story.append(Spacer(1, 6 * mm))
    story.append(_p("Inhalt", st["h2"]))
    story.append(toc)
    story.append(PageBreak())

    # -- 1 warnings ----------------------------------------------------------------
    story.append(_h("1 Hinweise und Warnungen", st["h1"], 0))
    if res.warnings:
        for text, rules in res.warnings:
            story.append(Paragraph("⚠ " + escape(text) + (f" <font size=7>({escape(', '.join(rules))})</font>" if rules else ""),
                                   st["warn"]))
    else:
        story.append(_p("Keine.", st["body"]))

    # -- 2 inputs ------------------------------------------------------------------
    story.append(_h("2 Eingangsdaten (aktuelle Stellschrauben)", st["h1"], 0))
    story.append(_p("Herkunft: Angabe = aus den persönlichen Daten; Annahme = unsicher; Planung = im Tool "
                    "eingestellt; abgeleitet = vom Tool hergeleitet. Die Spalte „XML“ nennt die Fundstelle in der Datei.",
                    st["small"]))
    for sec, rws in input_rows(res.raw_settings or s):
        story.append(_h(sec, st["h2"], 1))
        story.append(_table([["Stellschraube", "Wert", "Herkunft", "XML"]] + [list(r) for r in rws],
                            [55 * mm, 35 * mm, 22 * mm, W - 112 * mm], st))

    # -- 3 charts ------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_h("3 Diagramme", st["h1"], 0))
    th = charts.LIGHT
    cv = curves(res)
    story.append(_h("3.1 Gesamtsteuer über das zvE und Grenzwirkung (Knick)", st["h2"], 1))
    story.append(_fig_image(lambda f: charts.chart_kink(f, cv, th, focus_id, knick(res)), height_mm=200))
    if cv:
        story.append(_p(f"Abfindungsjahr {cv.year}: zvE {fmt_eur(cv.zve_now)}, Steuer {fmt_eur(cv.tax_now)}; Nullgrenze "
                        f"(zusätzlicher Abzug bis v + PV = 0) {fmt_eur(cv.nullgrenze)}.", st["small"]))
    story.append(_h("3.2 Zeitleiste", st["h2"], 1))
    story.append(_fig_image(lambda f: charts.chart_gantt(f, res, th), height_mm=130))
    story.append(_h("3.3 Liquidität", st["h2"], 1))
    story.append(_fig_image(lambda f: charts.chart_liquidity(f, res, th), height_mm=85))

    # -- 4 optimisation ----------------------------------------------------
    if optimizer_top:
        story.append(PageBreak())
        story.append(_h("4 Optimierung (Top-Kombinationen)", st["h1"], 0))
        for i, c in enumerate(optimizer_top):
            block = [_p(f"Rang {i + 1}: Saldo {fmt_eur(c.saldo)}", st["h3"]), _p(c.label, st["small"])]
            block += [_p("• " + line, st["body"]) for line in c.explanation.splitlines()]
            if c.rules:
                block.append(_p("Beteiligte Regeln: " + ", ".join(c.rules), st["small"]))
            story.append(KeepTogether(block))

    # -- 5 results with steps --------------------------------------------------------
    story.append(PageBreak())
    story.append(_h("5 Ergebnisse mit Rechenweg", st["h1"], 0))
    story.append(_p("Jeder Wert mit seiner Bedeutung, dem Rechenweg (Zahlen eingesetzt), Eingangsdaten mit Herkunft, verwendeten Parametern "
                    "(Jahr, Prüfstatus) und Regel-IDs. Die Regeln und Quellen stehen in Abschnitt 6.", st["small"]))
    groups: dict[str, list] = {}
    for t in res.rs.values():
        if not t.id.startswith(("warn_", "_")):
            groups.setdefault(t.group or "Übersicht", []).append(t)
    for g in sorted(groups, key=explain.group_sort_key(res.settings)):
        story.append(_h(g, st["h2"], 1))
        for t in groups[g]:
            e = explain.build(t, legal, res.rs)
            block = [Paragraph(f"<b>{escape(e.title)}</b> = <b>{escape(e.value)}</b>"
                               + (f" <font color='#9a4b00' size=7>[{escape(', '.join(e.flags))}]</font>" if e.flags else "")
                               + f" <font size=6 color='#777777'>({escape(e.id)})</font>", st["body"])]
            if e.meaning:
                block.append(Paragraph(f"<i>Bedeutung:</i> {escape(e.meaning)}", st["small"]))
            for k, step in enumerate(e.steps, 1):
                block.append(Paragraph(f"{k}. {escape(step)}", st["small"]))
            if e.note:
                block.append(Paragraph(f"<i>{escape(e.note)}</i>", st["small"]))
            if e.children:
                block.append(Paragraph("Abgeleitet aus: " + "; ".join(
                    f"{escape(lab)} = {escape(val)} ({escape(cid)})" for cid, lab, val in e.children), st["small"]))
            if e.inputs:
                block.append(_table([["Eingangswert", "Inhalt", "Herkunft", "XML"]] + [list(x) for x in e.inputs],
                                    [55 * mm, 30 * mm, 20 * mm, W - 105 * mm], st, zebra=False))
            if e.params:
                block.append(_table([["Parameter", "Bezeichnung", "Wert", "Jahr", "Status"]]
                                    + [[a, b, c, d, ", ".join(x for x in (ee, f) if x)] for a, b, c, d, ee, f in e.params],
                                    [48 * mm, 62 * mm, 28 * mm, 12 * mm, W - 150 * mm], st, zebra=False))
            if e.rules:
                block.append(Paragraph("Regeln: " + ", ".join(f"{escape(r.id)} ({escape(r.bezeichnung)})" for r in e.rules),
                                       st["small"]))
            block.append(Spacer(1, 2.5 * mm))
            story.append(KeepTogether(block[:3]))
            story.extend(block[3:])

    # -- 6 directory of rules, parameters, sources ---------------------------------------
    story.append(PageBreak())
    story.append(_h("6 Verzeichnis der Rechtsgrundlagen", st["h1"], 0))
    used_rules = sorted(res.tracer.used_rules)
    story.append(_h("6.1 Verwendete Regeln", st["h2"], 1))
    used_sources = set()
    for rid in used_rules:
        r = legal.rule(rid)
        if not r:
            continue
        block = [Paragraph(f"<b>{escape(r.id)}</b> – {escape(r.bezeichnung)} "
                           f"<font size=7 color='{'#2a7a2a' if r.geprueft else '#9a4b00'}'>"
                           f"({'geprüft' if r.geprueft else 'ungeprüft'})</font>", st["body"]),
                 _p(r.beschreibung, st["small"])]
        if r.formel:
            block.append(Paragraph(escape(r.formel).replace("\n", "<br/>"), st["mono"]))
        if r.unsicherheit:
            block.append(_p("Unsicherheit: " + r.unsicherheit, st["warn"]))
        for q in r.quellen:
            used_sources.add(q.quelle)
            block.append(_p(f"Quelle: {q.text} [{q.quelle}]", st["small"]))
        block.append(Spacer(1, 2 * mm))
        story.append(KeepTogether(block))

    story.append(_h("6.2 Verwendete Parameter", st["h2"], 1))
    data = [["Parameter", "Bezeichnung", "Wert", "gültig ab", "Status", "Quelle"]]
    seen = set()
    for key, p in sorted(res.tracer.used_params.items()):
        pid = p.id
        k = (pid, p.year_used)
        if k in seen:
            continue
        seen.add(k)
        entry = next((e for e in legal.params[pid] if e.gueltig_ab == p.year_used), legal.params[pid][0])
        for q in entry.quellen:
            used_sources.add(q.quelle)
        data.append([pid, entry.bezeichnung, explain._fmt_param_value(p.value, p.einheit), str(p.year_used or "–"),
                     ("geprüft" if p.geprueft else "ungeprüft"),
                     "; ".join(f"{q.text} [{q.quelle}]" for q in entry.quellen)])
    story.append(_table(data, [42 * mm, 48 * mm, 22 * mm, 13 * mm, 15 * mm, W - 140 * mm], st))
    story.append(_p("Hinweis: Werte für Jahre ohne eigenen Parameter werden mit dem letzten verfügbaren Wert fortgeschrieben "
                    "(im Rechenweg als „fortgeschrieben“ markiert).", st["small"]))

    story.append(_h("6.3 Einkommensteuertarif", st["h2"], 1))
    for y, tdef in sorted(legal.tariffs.items()):
        data = [["Zone", "Typ", "von", "bis", "Formel", "Koeffizienten"]]
        for z in tdef.zones:
            data.append([str(z.nr), z.typ, fmt_eur(float(z.lower)), fmt_eur(float(z.upper)) if z.upper is not None else "∞",
                         z.formel, ", ".join(f"{k} = {v}" for k, v in z.coeffs.items())])
        story.append(_p(f"Tarif {y} ({'geprüft' if tdef.geprueft else 'ungeprüft'}); {tdef.rundung}; {tdef.splitting}",
                        st["small"]))
        story.append(_table(data, [10 * mm, 25 * mm, 22 * mm, 22 * mm, 65 * mm, W - 144 * mm], st))
        for q in tdef.quellen:
            used_sources.add(q.quelle)

    story.append(_h("6.4 Quellen", st["h2"], 1))
    data = [["ID", "Art", "Fundstelle", "URL", "online geprüft"]]
    for sid in sorted(used_sources):
        src = legal.source(sid)
        if src:
            data.append([src.id, src.art, src.fundstelle, src.url or "–", "ja" if src.online_geprueft else "nein"])
    story.append(_table(data, [28 * mm, 22 * mm, 60 * mm, W - 128 * mm, 18 * mm], st))

    # -- 7 check instructions ------------------------------------------------------------
    story.append(_h("7 Hinweise zur Überprüfung", st["h1"], 0))
    for line in (
        "Für eine unabhängige Prüfung (z. B. mit einer KI oder Steuersoftware) eignen sich insbesondere:",
        "• Abschnitt 5, Ergebnis „Einkommensteuer <Jahr>“: Fallunterscheidung der Fünftelregelung mit Progressionsvorbehalt "
        "(R_Fuenftel_Progressionsvorbehalt, BFH VI R 44/07 und IX R 93/07) mit eingesetzten Zahlen nachrechnen.",
        "• Abschnitt 6.2: rechtliche Parameter mit dem Status „ungeprüft“ gegen die aktuellen Gesetzestexte (Links in 6.4) prüfen.",
        "• Abschnitt 2: Werte mit der Herkunft „Annahme“ durch belastbare Angaben ersetzen.",
        "• ALG-Zeitleiste (Sperrzeit, Ruhen nach § 158 SGB III, Anspruchsdauer) mit der Agentur für Arbeit, die "
        "KV-Behandlung der Abfindung mit der Krankenkasse abstimmen.",
        "• Vereinfachungen des Modells: vereinfachte Lohnsteuer (Steuerklassen V/VI angenähert), keine "
        "Einkommensteuer-Vorauszahlungen im Liquiditätsplan, Kinder bis 18 Jahre berücksichtigt, keine Kürzung der "
        "KV-Beiträge um den Krankengeldanteil.",
    ):
        story.append(_p(line, st["body"]))

    doc = _Doc(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
               title="Abfindungsoptimierer – Bericht", author="Abfindungsoptimierer", subject=DISCLAIMER)
    doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)
    return os.fspath(path)
