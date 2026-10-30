"""Tariff and Fünftelregelung tests (synthetic income figures only)."""

import pytest

from abfindung.engine.fifth_rule import est_fuenftel, est_regulaer
from abfindung.engine.tariff import Tariff


@pytest.fixture(scope="module")
def tariff(legal):
    return Tariff(legal, 2026)


def test_basic_allowance_is_tax_free(tariff, legal):
    gfb = legal.value("est_grundfreibetrag", 2026)
    assert tariff.grund(gfb) == 0
    assert tariff.grund(gfb + 100) > 0


def test_continuity_at_zone_limits(tariff):
    for z in tariff.zones:
        if z.upper is None:
            continue
        b = int(z.upper)
        jump = tariff.grund(b + 1) - tariff.grund(b)
        assert 0 <= jump <= 1, f"Sprung an Zonengrenze {b}: {jump}"


def test_monotone_and_marginal_rate_bounds(tariff):
    prev = 0
    for x in range(0, 400_000, 997):
        st = tariff.grund(x)
        assert st >= prev
        prev = st
    top = tariff.zones[-1].coeffs["a"]
    assert tariff.grund(1_000_001) - tariff.grund(1_000_000) <= float(top) + 1


def test_splitting(tariff):
    for x in (30_000, 80_001, 150_000, 600_000):
        assert tariff.st(x, True) == 2 * tariff.grund(x / 2)
        assert tariff.st(x, True) <= tariff.st(x, False)


def test_rounding_down(tariff):
    assert tariff.grund(50_000.99) == tariff.grund(50_000)
    assert isinstance(tariff.grund(50_000), int)


def test_carried_forward_and_indexed(legal):
    t = Tariff(legal, 2028, index_rate=0.02)
    assert t.fortgeschrieben and t.factor == pytest.approx(1.02 ** 2)
    base = Tariff(legal, 2026)
    assert t.grund(60_000) < base.grund(60_000)
    assert Tariff(legal, 2028).grund(60_000) == base.grund(60_000)


# -- Fünftelregelung -----------------------------------------------------------

def _normal(t, v, ae, joint=True):
    """R_Fuenftel_Normal: St(v) + 5 (St(v + AE/5) − St(v))."""
    return t.st(v, joint) + 5 * (t.st(v + ae / 5, joint) - t.st(v, joint))


def _negativ(t, v, ae, joint=True):
    """R_Fuenftel_Negativ: 5 St(zvE / 5)."""
    return 5 * t.st((v + ae) / 5, joint)


@pytest.mark.parametrize("v,ae", [(40_000, 100_000), (0, 250_000), (90_000, 300_000), (12_000, 30_000)])
def test_pv_zero_matches_normal(tariff, v, ae):
    r = est_fuenftel(v, ae, 0, tariff, True)
    assert abs(r.est - _normal(tariff, v, ae)) <= 5  # inner rounding of St(v + AE/5) only


@pytest.mark.parametrize("v,ae", [(-20_000, 200_000), (-5_000, 60_000)])
def test_pv_zero_matches_negative(tariff, v, ae):
    r = est_fuenftel(v, ae, 0, tariff, True)
    assert abs(r.est - _negativ(tariff, v, ae)) <= 5


def test_negative_v_alg_absorbed(tariff):
    """v < 0 and PV <= |v|: ALG is fully offset, tax equals the case without PV (BFH)."""
    base = est_fuenftel(-30_000, 250_000, 0, tariff, True).est
    for pv in (5_000, 20_000, 30_000):
        assert est_fuenftel(-30_000, 250_000, pv, tariff, True).est == base
    assert est_fuenftel(-30_000, 250_000, 40_000, tariff, True).est > base


def test_progression_increases_tax(tariff):
    a = est_fuenftel(50_000, 200_000, 0, tariff, True).est
    b = est_fuenftel(50_000, 200_000, 20_000, tariff, True).est
    assert b > a


def test_monotone_in_deduction(tariff):
    prev = None
    for d in range(0, 120_000, 500):
        e = est_fuenftel(60_000 - d, 300_000, 25_000, tariff, True).est
        if prev is not None:
            assert e <= prev + 1
        prev = e


def test_marginal_effect_higher_before_zero_limit(tariff):
    v, ae, pv = 20_000, 300_000, 15_000
    nullgrenze = v + pv  # deduction at which v + PV reaches zero
    def est(d):
        return est_fuenftel(v - d, ae, pv, tariff, True).est
    before = (est(0) - est(10_000)) / 10_000
    after = (est(nullgrenze + 5_000) - est(nullgrenze + 15_000)) / 10_000
    assert before > 0.6
    assert after < before / 2


def test_no_ae_regular(tariff):
    r = est_fuenftel(80_000, 0, 0, tariff, True)
    assert r.est == tariff.st(80_000, True)
    assert est_regulaer(80_000, 10_000, tariff, True).est > r.est
    assert est_fuenftel(-5, 0, 1000, tariff, True).est == 0
    assert est_fuenftel(-50_000, 20_000, 0, tariff, True).est == 0
