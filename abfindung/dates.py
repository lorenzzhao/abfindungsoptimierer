# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Date helpers (calendar arithmetic used by the timeline and the UI)."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from functools import lru_cache

MONTHS_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


@lru_cache(maxsize=1024)
def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def end_of_month(d: date) -> date:
    return date(d.year, d.month, days_in_month(d.year, d.month))


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, days_in_month(y, m)))


def add_years(d: date, n: int) -> date:
    return add_months(d, 12 * n)


def months_between(a: date, b: date) -> int:
    """Number of full months from a to b (0 if b < a)."""
    if b < a:
        return 0
    n = (b.year - a.year) * 12 + (b.month - a.month)
    if add_months(a, n) > b:
        n -= 1
    return max(0, n)


def age_on(birth: date, d: date) -> int:
    return d.year - birth.year - ((d.month, d.day) < (birth.month, birth.day))


def iter_days(a: date, b: date):
    d = a
    one = timedelta(days=1)
    while d <= b:
        yield d
        d += one


def month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def from_month_index(idx: int) -> tuple[int, int]:
    return idx // 12, idx % 12 + 1


def fmt_date(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "–"


def fmt_month(year: int, month: int) -> str:
    return f"{MONTHS_DE[month - 1]} {year}"


def parse_date(s: str) -> date:
    return date.fromisoformat(s.strip()[:10])


def fmt_eur(x: float | None, dec: int = 0) -> str:
    if x is None:
        return "–"
    s = f"{x:,.{dec}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"


def fmt_num(x: float, dec: int = 2) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_pct(x: float, dec: int = 2) -> str:
    return fmt_num(x * 100, dec) + " %"
