# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Charts (matplotlib, object API without pyplot) – used by the GUI and the PDF report.

- 'Knick': total tax over zvE and marginal effect of a deduction, Nullgrenze marked
- Timeline per person (Gantt)
- Monthly liquidity
"""

from __future__ import annotations

from datetime import date, timedelta

import matplotlib
from matplotlib.dates import DateFormatter, MonthLocator, date2num
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .dates import fmt_eur
from .engine.timeline import STATUS_LABEL

matplotlib.rcParams["font.family"] = "DejaVu Sans"

# Okabe-Ito (colour-blind safe)
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#7F7F7F"]

STATUS_COLOR = {
    "beschaeftigt": "#0072B2",
    "freigestellt": "#56B4E9",
    "sperrzeit": "#D55E00",
    "ruhen_158": "#CC79A7",
    "ruhen_157": "#E69F00",
    "alg_bezug": "#009E73",
    "ohne_leistung": "#BBBBBB",
    "neue_beschaeftigung": "#332288",
}

LIGHT = {"bg": "#ffffff", "fg": "#222222", "grid": "#dddddd", "accent": "#0072B2", "focus": "#D55E00", "muted": "#888888"}
DARK = {"bg": "#1f2328", "fg": "#e6e6e6", "grid": "#3a3f45", "accent": "#56B4E9", "focus": "#F0A050", "muted": "#9aa0a6"}

EUR_FMT = FuncFormatter(lambda x, _: fmt_eur(x).replace(" €", "") if abs(x) < 1e6 else f"{x / 1e6:.1f} Mio")


def _style(fig: Figure, ax_list, th: dict) -> None:
    fig.set_facecolor(th["bg"])
    for ax in ax_list:
        ax.set_facecolor(th["bg"])
        ax.tick_params(colors=th["fg"], labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(th["grid"])
        ax.yaxis.label.set_color(th["fg"])
        ax.xaxis.label.set_color(th["fg"])
        ax.title.set_color(th["fg"])
        ax.grid(True, color=th["grid"], linewidth=0.6, alpha=0.8)
        ax.set_axisbelow(True)


def _legend(ax, th, **kw):
    lg = ax.legend(fontsize=8, frameon=False, **kw)
    if lg:
        for t in lg.get_texts():
            t.set_color(th["fg"])


def chart_kink(fig: Figure, cv, th: dict, focus_id: str | None = None, kn=None) -> None:
    """Top: total tax over the zvE. Bottom (Ä8): additional tax per extra euro over the remaining zvE,
    three lines, Nullgrenze markers, current plan, value table."""
    fig.clear()
    if cv is None:
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, "Keine außerordentlichen Einkünfte im Horizont", ha="center", va="center", color=th["fg"])
        _style(fig, [ax], th)
        return
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 3.4, 0.95], hspace=0.5)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    ax3 = fig.add_subplot(gs[2])
    ax1.plot(cv.zve, cv.tax, color=th["accent"], lw=2, label="mit Fünftelregelung" + (" + Progressionsvorbehalt (ALG)" if cv.alg > 0 else ""))
    ax1.plot(cv.zve, cv.tax_regular, color=th["muted"], lw=1, ls="--", label="ohne Fünftelregelung (überschlägig)")
    ax1.axvline(cv.zve_now, color=th["focus"], lw=1.5 if focus_id else 1, ls="-")
    ax1.scatter([cv.zve_now], [cv.tax_now], color=th["focus"], zorder=5, s=40 if focus_id else 25)
    ax1.annotate(f"aktuell: zvE {fmt_eur(cv.zve_now)}\nSteuer {fmt_eur(cv.tax_now)}", (cv.zve_now, cv.tax_now),
                 textcoords="offset points", xytext=(8, -28), fontsize=7, color=th["fg"])
    if cv.nullgrenze > 0:
        ax1.axvline(cv.zve_nullgrenze, color=PALETTE[2], lw=1.2, ls=":")
        ax1.annotate("Nullgrenze\n(v + PV = 0)" if cv.alg > 0 else "Nullgrenze\n(v = 0)", (cv.zve_nullgrenze, max(cv.tax)), textcoords="offset points",
                     xytext=(-4, -4), ha="right", va="top", fontsize=7, color=PALETTE[2])
    ax1.set_title(f"Gesamtsteuer im Abfindungsjahr {cv.year} in Abhängigkeit vom zvE", fontsize=10)
    ax1.set_xlabel("zu versteuerndes Einkommen (€)", fontsize=8)
    ax1.set_ylabel("ESt + Soli + KiSt (€)", fontsize=8)
    ax1.xaxis.set_major_formatter(EUR_FMT)
    ax1.yaxis.set_major_formatter(EUR_FMT)
    _legend(ax1, th, loc="upper left")
    axes = [ax1, ax2]
    if kn is not None:
        _knick_axes(ax2, kn, th)
        _knick_table(ax3, kn, th)
    else:
        ax2.set_axis_off()
    ax3.set_axis_off()
    _style(fig, axes, th)
    fig.subplots_adjust(left=0.1, right=0.9, top=0.95, bottom=0.03)
    fig._knick = kn  # used by the GUI tooltip (x, y and zone)
    fig._knick_ax = ax2


KNICK_COLORS = (PALETTE[0], PALETTE[1], PALETTE[3])


def _knick_axes(ax, kn, th) -> None:
    from .engine.marginal import LINE_LABELS

    for (lab, ys), col in zip(kn.lines.items(), KNICK_COLORS):
        ls = "--" if lab == LINE_LABELS[2] else "-"  # second encoding besides the colour
        ax.plot(kn.x, ys, color=col, lw=1.8, ls=ls, label=lab)
        k = int(len(kn.x) * (0.62 + 0.1 * list(kn.lines).index(lab)))  # direct label inside the plot
        ax.annotate(lab, (kn.x[k], ys[k]), textcoords="offset points", xytext=(0, 6), fontsize=6.5, color=col,
                    ha="center", va="bottom")
    ax.axvline(0, color=th["muted"], lw=1, ls=":")
    ax.annotate("Nullgrenze ohne ALG" if kn.alg > 0 else "Nullgrenze", (0, 1), xycoords=("data", "axes fraction"), xytext=(3, -3),
                textcoords="offset points", fontsize=6.5, color=th["muted"], va="top")
    if kn.alg > 0:
        ax.axvline(-kn.alg, color=th["muted"], lw=1, ls=":")
        ax.annotate("Nullgrenze mit ALG", (-kn.alg, 1), xycoords=("data", "axes fraction"), xytext=(-3, -3),
                    textcoords="offset points", fontsize=6.5, color=th["muted"], va="top", ha="right")
    ax.scatter([kn.v_now], [kn.y_now], color=th["focus"], zorder=5, s=30)
    ax.annotate(f"aktuelle Planung: übriges zvE {fmt_eur(kn.v_now)} → {kn.y_now:.0f} %", (kn.v_now, kn.y_now),
                textcoords="offset points", xytext=(6, 8), fontsize=7, color=th["fg"])
    ax.set_xlim(kn.x[0], kn.x[-1])
    ax.set_ylim(0, max(10, max(max(v) for v in kn.lines.values()) * 1.12))
    ax.set_title(f"Mehrsteuer je zusätzlichem Euro im Abfindungsjahr {kn.year} (nur ESt, ohne Soli und Günstigerprüfung)",
                 fontsize=9)
    ax.set_xlabel("übriges zvE ohne Abfindung, nach Kinderfreibeträgen (€)", fontsize=8)
    ax.set_ylabel("Grenzbelastung (%)", fontsize=8)
    ax.xaxis.set_major_formatter(EUR_FMT)
    ax.grid(True, alpha=0.4)
    _legend(ax, th, loc="upper right")


def _knick_table(ax, kn, th) -> None:
    from .engine.marginal import KNICK_POINTS

    head = ["übriges zvE"] + [f"{p / 1000:+.0f} T€".replace("+0 ", "0 ") for p in KNICK_POINTS]
    rows = [[lab] + [f"{kn.table[lab][p]:.0f} %" for p in KNICK_POINTS] for lab in kn.table]
    t = ax.table(cellText=rows, colLabels=head, loc="upper center", cellLoc="center")
    t.auto_set_font_size(False)
    t.set_fontsize(6.5)
    t.scale(1, 1.05)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor(th["grid"])
        cell.set_facecolor(th["bg"])
        cell.get_text().set_color(KNICK_COLORS[r - 1] if r > 0 and c == 0 else th["fg"])
        if c == 0:
            cell.set_width(0.2)
            cell.get_text().set_ha("left")


# 4 -------------------------------------------------------------------------------
# important dates in the timeline: kind -> (marker, filled, colour (None: red for deadlines, "fg": text colour), side,
# legend text). Deadlines and registrations above the bar, other events below it.
EVENT_STYLE = {
    "arbeitsuchend_frist": ("v", True, None, "top", "spätestens arbeitsuchend melden"),
    "arbeitsuchend_plan": ("v", False, None, "top", "Arbeitsuchendmeldung geplant (rot: zu spät)"),
    "arbeitslos_frist": ("D", True, None, "top", "spätestens arbeitslos melden"),
    "arbeitslos_plan": ("D", False, None, "top", "Arbeitslosmeldung geplant (rot: zu spät)"),
    "abfindung": ("$€$", True, "fg", "bottom", "Abfindung gezahlt (Monat)"),
    "freistellung": (">", True, STATUS_COLOR["freigestellt"], "bottom", "Beginn der Freistellung"),
    "ende": ("|", True, STATUS_COLOR["beschaeftigt"], "bottom", "Ende Arbeitsverhältnis"),
    "fristende": ("|", False, STATUS_COLOR["ruhen_158"], "bottom",
                  "fiktives Ende Kündigungsfrist"),
    "alg_start": ("^", True, STATUS_COLOR["alg_bezug"], "bottom", "ALG-Beginn"),
    "alg_end": ("^", False, STATUS_COLOR["alg_bezug"], "bottom", "letzter ALG-Tag"),
    "erloeschen": ("x", True, STATUS_COLOR["alg_bezug"], "bottom", "ALG-Anspruch erlischt"),
    "newjob": ("s", True, STATUS_COLOR["neue_beschaeftigung"], "bottom", "neue Beschäftigung"),
}


def timeline_events(ps, tl, payments=()) -> list[tuple]:
    """Important dates of a person for the timeline: [(date, kind)] (kinds: keys of EVENT_STYLE).
    ``payments``: [(month index, amount)] of the severance. Planned registrations only when they differ from the
    deadline; ALG dates only when ALG is claimed."""
    ev = []
    if not ps.austritt:
        if ps.newjob:
            ev.append((ps.newjob_start, "newjob"))
        return ev
    for mi, amount in payments:
        if amount:
            ev.append((date(mi // 12, mi % 12 + 1, 15), "abfindung"))
    if tl.freistellung_ab:
        ev.append((tl.freistellung_ab, "freistellung"))
    ev.append((tl.end, "ende"))
    if ps.alg_aktiv:
        if tl.meldefrist:
            ev.append((tl.meldefrist, "arbeitsuchend_frist"))
            if ps.arbeitsuchend_datum != tl.meldefrist:
                ev.append((ps.arbeitsuchend_datum, "arbeitsuchend_plan"))
        first_unemployed = tl.end + timedelta(days=1)
        ev.append((first_unemployed, "arbeitslos_frist"))
        if ps.meldung != first_unemployed:
            ev.append((ps.meldung, "arbeitslos_plan"))
        if tl.ruhen158 and tl.fristende and tl.fristende > tl.end:
            ev.append((tl.fristende, "fristende"))
        if tl.alg_start:
            ev.append((tl.alg_start, "alg_start"))
            if tl.alg_end:
                ev.append((tl.alg_end, "alg_end"))
            if tl.erloeschen:
                ev.append((tl.erloeschen, "erloeschen"))
    if ps.newjob:
        ev.append((ps.newjob_start, "newjob"))
    return ev


ROW_GAP = 1.9  # distance of the person rows: dates above and below each bar


def chart_gantt(fig: Figure, res, th: dict, focus_id: str | None = None) -> None:
    fig.clear()
    ax = fig.add_subplot(111)
    s = res.settings
    start = date(s.options.horizon_start, 1, 1)
    end = date(s.options.horizon_end, 12, 31)
    persons = s.persons
    used = set()
    overlay_used = set()
    # how many days a date label covers on this axis (about 8 characters at 6 pt plus a gap)
    ax.set_xlim(date2num(start), date2num(end))
    width_px = max(ax.get_window_extent().width, 1.0)
    label_days = int((44 * fig.dpi / 72) / width_px * (end - start).days) + 1
    kv_used = False
    for row, ps in enumerate(persons):
        tl = res.ctx.timelines[ps.id]
        seg_start, seg_status = None, None
        segs = []
        for d, day in tl.days.items():
            if d < start or d > end:
                continue
            if day.status != seg_status:
                if seg_status is not None:
                    segs.append((seg_start, d, seg_status))
                seg_start, seg_status = d, day.status
        if seg_status is not None:
            segs.append((seg_start, end + timedelta(days=1), seg_status))
        y = ROW_GAP * (len(persons) - 1 - row)
        focused = bool(focus_id and ps.id in focus_id)
        for a, b, st in segs:
            ax.barh(y, date2num(b) - date2num(a), left=date2num(a), height=0.5, color=STATUS_COLOR[st],
                    edgecolor=th["focus"] if focused else th["bg"], linewidth=1.5 if focused else 0.3,
                    label=STATUS_LABEL[st] if st not in used else None)
            used.add(st)
        # overlay: Sperrzeit / Ruhen in parallel (thin bars)
        for flag, col, off in (("sperr", STATUS_COLOR["sperrzeit"], 0.3), ("r158", STATUS_COLOR["ruhen_158"], 0.36)):
            if not (ps.austritt and ps.alg_aktiv):
                continue
            run_start = None
            for d, day in tl.days.items():
                if d < start or d > end:
                    continue
                on = getattr(day, flag)
                if on:
                    overlay_used.add(flag)
                if on and run_start is None:
                    run_start = d
                if not on and run_start is not None:
                    ax.barh(y + off, date2num(d) - date2num(run_start), left=date2num(run_start), height=0.06, color=col)
                    run_start = None
            if run_start is not None:
                ax.barh(y + off, date2num(end) - date2num(run_start), left=date2num(run_start), height=0.06, color=col)
        # important dates: deadlines above the bar, other events below it, each with its date
        events = sorted(timeline_events(ps, tl, res.ctx.payments.get(ps.id, ())))
        deadline = {k: d for d, k in events if k.endswith("_frist")}
        levels: dict[str, list] = {"top": [], "bottom": []}  # side -> date up to which each label level is taken
        sim_last = max(tl.days) if tl.days else end
        for d, kind in events:
            if not start <= d <= end or (kind == "alg_end" and d >= sim_last):  # still running at the end
                continue
            marker, filled, colour, side, label = EVENT_STYLE[kind]
            late = colour is None and not filled and d > deadline.get(kind.replace("_plan", "_frist"), d)
            if colour is None:
                col = "#d32f2f" if (filled or late) else th["fg"]
            else:
                col = th["fg"] if colour == "fg" else colour
            x = date2num(d)
            top = side == "top"
            ym = y + 0.46 if top else y - 0.5
            ax.plot([x, x], [y - 0.25 if top else y + 0.25, ym], color=col, lw=0.7, ls="-" if filled else ":",
                    alpha=0.8)
            ax.plot(x, ym, marker=marker, ms=7 if kind == "abfindung" else 6, color=col,
                    mfc=col if filled else "none", mew=1.6 if marker == "|" else 1, ls="",
                    label=label if kind not in used else None)
            used.add(kind)
            free = [i for i, busy in enumerate(levels[side]) if d > busy]  # lowest label level that is free here
            level = free[0] if free else min(len(levels[side]), 3)
            if level == len(levels[side]):
                levels[side].append(d)
            levels[side][level] = d + timedelta(days=label_days)
            text = d.strftime("%m/%y") if kind == "abfindung" else d.strftime("%d.%m.%y")
            ax.annotate(text, (x, ym), xytext=(5, (3 + 7 * level) if top else -(9 + 7 * level)),
                        textcoords="offset points", ha="left", fontsize=6, color=col)
        # KV own contributions (dots)
        kv = res.ctx.kv[ps.id]
        for (yy, mm), km in kv.months.items():
            if km.own > 0 and start <= date(yy, mm, 15) <= end:
                ax.plot(date2num(date(yy, mm, 15)), y - 0.36, marker="s", ms=3, color=th["fg"])
                kv_used = True
    for flag, st, lab in (("sperr", "sperrzeit", "Sperrzeit läuft (dünne Linie)"),
                          ("r158", "ruhen_158", "Ruhen § 158 läuft (dünne Linie)")):
        if flag in overlay_used and st not in used:  # same colour as the status bar: one legend entry is enough
            ax.barh(0, 0, height=0.06, color=STATUS_COLOR[st], label=lab)
    if kv_used:
        ax.plot([], [], marker="s", ms=3, ls="", color=th["fg"], label="eigener KV-Beitrag im Monat")
    ax.set_ylim(-1.1, ROW_GAP * (len(persons) - 1) + 0.85)  # room for the markers and dates above and below
    ax.set_yticks([ROW_GAP * i for i in range(len(persons))])
    ax.set_yticklabels([p.label for p in reversed(persons)], fontsize=8)
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    step = next(m for m in (3, 6, 12) if months / m <= fig.get_figwidth() * 1.7)  # tick labels must not overlap
    ax.xaxis.set_major_locator(MonthLocator(bymonth=range(1, 13, step)))
    ax.xaxis.set_major_formatter(DateFormatter("%m/%y"))
    ax.set_xlim(date2num(start), date2num(end))
    ax.set_title("Zeitleiste (Status je Tag; Sperrzeit und Ruhen parallel als dünne Linien)", fontsize=10)
    _style(fig, [ax], th)
    ncol = max(2, min(4, int(fig.get_figwidth() / 2.6)))  # legend columns that fit the width (about 2.6 in each)
    _legend(ax, th, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=ncol)
    fig.tight_layout()


# 5 -------------------------------------------------------------------------------
def chart_liquidity(fig: Figure, res, th: dict, focus_id: str | None = None) -> None:
    fig.clear()
    ax = fig.add_subplot(111)
    rows = res.liquidity
    if not rows:
        return
    xs = list(range(len(rows)))
    keys = [("gehalt", "Nettogehalt"), ("abfindung", "Abfindung netto LSt"), ("alg", "ALG"), ("kv", "eigene KV/PV"),
            ("gestaltung", "Gestaltungen"), ("steuer", "Erstattung/Nachzahlung")]
    pos = [0.0] * len(rows)
    neg = [0.0] * len(rows)
    for j, (k, lab) in enumerate(keys):
        vals = [r[k] for r in rows]
        bottoms = [pos[i] if v >= 0 else neg[i] for i, v in enumerate(vals)]
        ax.bar(xs, vals, bottom=bottoms, color=PALETTE[j], label=lab, width=0.8)
        for i, v in enumerate(vals):
            if v >= 0:
                pos[i] += v
            else:
                neg[i] += v
    ax.plot(xs, [r["kumuliert"] for r in rows], color=th["fg"], lw=1.5, label="kumuliert (Kontostand seit Horizontbeginn)")
    if res.liq_min_month:
        i = next(i for i, r in enumerate(rows) if (r["jahr"], r["monat"]) == res.liq_min_month)
        ax.scatter([i], [res.liq_min], color=th["focus"], zorder=5, s=40 if focus_id == "liq_min" else 20)
    ax.set_xticks(xs[::3])
    ax.set_xticklabels([f"{r['monat']:02d}/{str(r['jahr'])[2:]}" for r in rows][::3], fontsize=7)
    ax.yaxis.set_major_formatter(EUR_FMT)
    ax.axhline(0, color=th["muted"], lw=0.8)
    ax.set_title("Liquidität je Monat (Balken) und kumuliert (Linie, gleiche Achse)", fontsize=10)
    _style(fig, [ax], th)
    _legend(ax, th, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4)
    fig.tight_layout()
