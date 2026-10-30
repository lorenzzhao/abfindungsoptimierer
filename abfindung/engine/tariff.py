# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Income tax tariff § 32a EStG, built from the zones in the legal XML.

Rounding (§ 32a Abs. 1 Satz 1 and 6 EStG): zvE and tax are rounded down to full euros.
Splitting (§ 32a Abs. 5 EStG): 2 x tariff(zvE / 2).

For years without their own tariff the latest earlier tariff is carried forward
(flag ``fortgeschrieben``). Optionally it can be indexed by an annual rate g:
St_t(x) = f * St(x / f) with f = (1 + g)^(t - base year), i.e. all zone limits scale by f.
"""

from __future__ import annotations

import math
from decimal import ROUND_FLOOR, Decimal

_TEN_K = Decimal(10000)


class Tariff:
    def __init__(self, legal, year: int, index_rate: float = 0.0):
        tdef, fortg = legal.tariff(year)
        self.tdef = tdef
        self.year = year
        self.base_year = tdef.year
        self.fortgeschrieben = fortg
        n = year - tdef.year if year > tdef.year else 0
        self.factor = (1.0 + index_rate) ** n if n else 1.0
        self.zones = tdef.zones
        self._cache: dict[int, int] = {}

    # -- core ---------------------------------------------------------------
    def _raw(self, x: int) -> int:
        """Basic tariff (Grundtarif) for an integer zvE, R: § 32a Abs. 1 EStG."""
        if x <= 0:
            return 0
        c = self._cache.get(x)
        if c is not None:
            return c
        zone = self.zones[-1]
        for z in self.zones:
            if x >= z.lower and (z.upper is None or x <= z.upper):
                zone = z
                break
        dx = Decimal(x)
        k = zone.coeffs
        if zone.typ == "steuerfrei":
            est = Decimal(0)
        elif zone.typ in ("progression_y", "progression_z"):
            t = (dx - zone.offset) / _TEN_K
            est = (k.get("a", Decimal(0)) * t + k.get("b", Decimal(0))) * t + k.get("c", Decimal(0))
        elif zone.typ == "linear":
            est = k.get("a", Decimal(0)) * dx - k.get("b", Decimal(0))
        else:  # pragma: no cover - schema restricts the types
            raise ValueError(f"Unbekannter Zonentyp {zone.typ}")
        val = int(est.to_integral_value(rounding=ROUND_FLOOR))
        val = max(0, val)
        self._cache[x] = val
        return val

    def grund(self, x: float) -> int:
        """Grundtarif with rounding of zvE and tax (and optional indexation)."""
        xi = math.floor(x)
        if xi <= 0:
            return 0
        if self.factor != 1.0:
            return math.floor(self.factor * self._raw(math.floor(xi / self.factor)))
        return self._raw(xi)

    def st(self, x: float, joint: bool) -> int:
        """Tax on zvE x; splitting for joint assessment."""
        xi = math.floor(x)
        if xi <= 0:
            return 0
        if joint:
            return 2 * self.grund(xi / 2)
        return self.grund(xi)

    def rate(self, x: float, joint: bool) -> float:
        """Average rate satz(x) = St(x) / x, 0 for x <= 0."""
        xi = math.floor(x)
        if xi <= 0:
            return 0.0
        return self.st(xi, joint) / xi

    def describe(self) -> str:
        s = f"Tarif {self.base_year}"
        if self.fortgeschrieben:
            s += f" (fortgeschrieben auf {self.year}"
            if self.factor != 1.0:
                s += f", indexiert mit Faktor {self.factor:.4f}"
            s += ")"
        return s


_cache: dict[tuple, Tariff] = {}


def get_tariff(legal, year: int, index_rate: float = 0.0) -> Tariff:
    key = (id(legal), year, round(index_rate, 6))
    t = _cache.get(key)
    if t is None:
        if len(_cache) > 64:
            _cache.clear()
        t = _cache[key] = Tariff(legal, year, index_rate)
    return t
