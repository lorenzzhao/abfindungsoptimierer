"""Ä8–Ä10: Knick chart data, tax-free base, warnings."""

from pathlib import Path

import pytest

from abfindung.engine.fifth_rule import est_fuenftel
from abfindung.engine.marginal import KNICK_POINTS, LINE_LABELS, knick
from abfindung.engine.scenario import run
from abfindung.engine.settings import add_gestaltung, from_personal
from abfindung.engine.tariff import Tariff
from abfindung.io import load_personal

from .helpers import apply_scenario, apply_variant, set_basisrente

FIXTURE = Path(__file__).parent / "fixtures" / "fiktiv_paar.xml"


def test_tax_free_base_of_fifth_rule(legal):
    """Ä9: joint, remaining zvE 0, no ALG, severance = 5 × 2 × basic allowance → no tax.
    With integer rounding of the tariff (§ 32a), the first euros above stay tax-free as well;
    1.000 € more clearly leads to tax."""
    t = Tariff(legal, 2026)
    gfb = legal.value("est_grundfreibetrag", 2026)
    ae = 5 * 2 * gfb
    assert est_fuenftel(0, ae, 0, t, True).est == 0
    assert est_fuenftel(0, ae + 1000, 0, t, True).est > 0


def test_sockel_shown(legal):
    s = from_personal(load_personal(FIXTURE), legal)
    apply_variant(s, "F")
    apply_scenario(s, "S2")
    r = run(s, legal, extras=False)
    assert any(k.startswith("sockel_") for k in r.rs)


def test_knick_reference_values(legal):
    """Marginal burden table (severance 180.000 €, ALG 21.000 €, splitting, tariff 2027); regression values."""
    ref = {LINE_LABELS[0]: (0, 0, 0, 0, 0, 0, 25, 32, 39),
           LINE_LABELS[1]: (15, 21, 22, 120, 129, 138, 56, 63, 56),
           LINE_LABELS[2]: (15, 104, 81, 112, 89, 71, 64, 66, 44)}
    s = from_personal(load_personal(FIXTURE), legal)
    r = run(s, legal, extras=False)
    u = r.main_unit_year()
    u.ae, u.pv, u.joint = 180_000, 21_000, True
    u.tariff = Tariff(legal, 2027)
    kn = knick(r)
    for lab, vals in ref.items():
        for p, want in zip(KNICK_POINTS, vals):
            assert kn.table[lab][p] == pytest.approx(want, abs=1), (lab, p)


def test_deduction_beyond_zero_limit_warns(legal):
    s = from_personal(load_personal(FIXTURE), legal)
    apply_variant(s, "A")
    s.veranlagung[2027] = "zusammen"
    set_basisrente(s, {2027: 20_000})
    add_gestaltung(s, "erhaltung", 2027, betrag=80_000)  # together far beyond the Nullgrenze (about 47.000)
    r = run(s, legal, extras=False)
    assert any("über die Nullgrenze hinaus" in w for w, _ in r.warnings)
