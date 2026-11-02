"""Automated checks of the LCCA engine against independent closed-form (hand) formulas.

Run:  python -m pytest -q        (or)   python -m unittest discover -s tests -v
Every expected value below is computed from textbook factors written out explicitly in the test,
NOT by calling the engine, so the tests detect formula errors in the engine.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcca import (Alternative, CostItem, SolarCase, SlabTariff, build_alternatives,  # noqa: E402
                  breakeven_discount_rate, cashflow_table, crf, discounted_payback, lcc,
                  net_savings, pm_surya_ghar_cfa, spw, tornado_items, tornado_parameters, upw,
                  upw_escalating, real_rate)
from lcca.io import project_from_json, project_to_json  # noqa: E402

TOL = 0.01  # rupees


def P_A(d, n):
    return (1 - (1 + d) ** -n) / d


class TestFactors(unittest.TestCase):
    def test_textbook_values(self):
        # (P/A, 7%, 25) = 11.6536 ; (P/F, 7%, 12) = 0.4440 ; (A/P, 7%, 25) = 0.08581
        self.assertAlmostEqual(upw(0.07, 25), 11.653583, places=5)
        self.assertAlmostEqual(spw(0.07, 12), 0.444012, places=5)
        self.assertAlmostEqual(crf(0.07, 25), 0.085811, places=5)

    def test_zero_rate(self):
        self.assertEqual(upw(0.0, 10), 10.0)
        self.assertAlmostEqual(crf(0.0, 10), 0.1)
        self.assertEqual(upw_escalating(0.05, 0.05, 20), 20.0)

    def test_fisher(self):
        self.assertAlmostEqual(real_rate(0.07, 0.04), 1.07 / 1.04 - 1)

    def test_escalating_equals_real_rate_form(self):
        # nominal d with escalation e == real-rate discounting with differential escalation
        d, e, i, n = 0.07, 0.03, 0.04, 25
        r = (1 + d) / (1 + i) - 1
        ed = (1 + e) / (1 + i) - 1
        direct = sum(((1 + ed) / (1 + r)) ** t for t in range(1, n + 1))
        self.assertAlmostEqual(upw_escalating(d, e, n), direct, places=9)


class TestItems(unittest.TestCase):
    def test_annual_constant(self):
        a = Alternative("x", [CostItem("m", "annual", 1000)])
        self.assertAlmostEqual(lcc(a, 20, 0.08), 1000 * P_A(0.08, 20), delta=TOL)

    def test_annual_escalating(self):
        a = Alternative("x", [CostItem("m", "annual", 1000, escalation=0.05)])
        x = 1.05 / 1.08
        self.assertAlmostEqual(lcc(a, 20, 0.08), 1000 * x * (1 - x ** 20) / (1 - x), delta=TOL)

    def test_once(self):
        a = Alternative("x", [CostItem("o", "once", 5000, year=10)])
        self.assertAlmostEqual(lcc(a, 20, 0.08), 5000 / 1.08 ** 10, delta=TOL)

    def test_capital_longer_than_period_gets_residual(self):
        a = Alternative("x", [CostItem("c", "capital", 100000, life=40, replace=False)])
        expected = 100000 - 100000 * (15 / 40) / 1.06 ** 25
        self.assertAlmostEqual(lcc(a, 25, 0.06), expected, delta=TOL)

    def test_replacement_exactly_at_end_is_not_bought(self):
        a = Alternative("x", [CostItem("c", "capital", 1000, life=10)])
        cf = cashflow_table(a, 20, 0.05)
        self.assertEqual(sorted(cf["year"].tolist()), [0, 10])        # no buy at 20, no residual
        self.assertAlmostEqual(lcc(a, 20, 0.05), 1000 + 1000 / 1.05 ** 10, delta=TOL)

    def test_capital_starting_late_with_two_replacements_and_residual(self):
        a = Alternative("x", [CostItem("inv", "capital", 20000, year=12, life=12)])
        expected = 20000 / 1.07 ** 12 + 20000 / 1.07 ** 24 - 20000 * 11 / 12 / 1.07 ** 25
        self.assertAlmostEqual(lcc(a, 25, 0.07), expected, delta=TOL)

    def test_capital_escalation(self):
        a = Alternative("x", [CostItem("c", "capital", 1000, life=10, escalation=0.03)])
        expected = 1000 + 1000 * 1.03 ** 10 / 1.06 ** 10 + 1000 * 1.03 ** 20 / 1.06 ** 20 \
            - 1000 * (5 / 10) * 1.03 ** 25 / 1.06 ** 25
        self.assertAlmostEqual(lcc(a, 25, 0.06), expected, delta=TOL)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            lcc(Alternative("x", [CostItem("c", "capital", 1, life=0)]), 10, 0.05)
        with self.assertRaises(ValueError):
            lcc(Alternative("x", [CostItem("o", "once", 1, year=11)]), 10, 0.05)
        with self.assertRaises(ValueError):
            lcc(Alternative("x", [CostItem("a", "annual", 1, start=5, end=3)]), 10, 0.05)
        with self.assertRaises(ValueError):
            lcc(Alternative("x", [CostItem("b", "bogus", 1)]), 10, 0.05)

    def test_zero_discount_rate_is_plain_sum(self):
        a = Alternative("x", [CostItem("i", "once", 100), CostItem("m", "annual", 10)])
        self.assertAlmostEqual(lcc(a, 10, 0.0), 200, delta=TOL)


class TestSyntheticFlooring(unittest.TestCase):
    """Second validation case (illustrative numbers): unequal lives, replacements, residuals."""

    def setUp(self):
        self.N, self.d = 30, 0.08
        self.x = Alternative("Tile", [CostItem("Tile floor", "capital", 150000, life=20),
                                      CostItem("Maintenance", "annual", 2000)])
        self.y = Alternative("Epoxy", [CostItem("Epoxy floor", "capital", 90000, life=8),
                                       CostItem("Maintenance", "annual", 3000)])

    def test_hand_values(self):
        d = self.d
        lx = 150000 + 150000 / (1 + d) ** 20 - 150000 * (10 / 20) / (1 + d) ** 30 + 2000 * P_A(d, 30)
        ly = (90000 * (1 + (1 + d) ** -8 + (1 + d) ** -16 + (1 + d) ** -24)
              - 90000 * (2 / 8) / (1 + d) ** 30 + 3000 * P_A(d, 30))
        self.assertAlmostEqual(lcc(self.x, self.N, d), lx, delta=TOL)
        self.assertAlmostEqual(lcc(self.y, self.N, d), ly, delta=TOL)

    def test_breakeven_root_zeroes_net_savings(self):
        roots = breakeven_discount_rate(self.x, self.y, self.N)
        for r in roots:
            self.assertAlmostEqual(net_savings(self.x, self.y, self.N, r), 0.0, delta=1.0)


class TestSolarBenchmark(unittest.TestCase):
    """The team benchmark (MSEDCL residential, 300 kWh/month, 2 kWp PV, 25 yr, 7%)."""

    def setUp(self):
        self.case = SolarCase()
        self.a, self.b, self.et = build_alternatives(self.case)

    def test_slab_bill_300_units(self):
        # 100x3.96 + 200x10.80 = 2556 ; wheeling 480 ; fixed 130 ; duty 16% -> 3672.56
        self.assertAlmostEqual(SlabTariff().monthly_bill(300)["total"], 3672.56, delta=TOL)

    def test_slab_bill_boundaries(self):
        t = SlabTariff()
        self.assertAlmostEqual(t.monthly_bill(0)["total"], 130 * 1.16, delta=TOL)
        self.assertAlmostEqual(t.monthly_bill(100)["energy"], 396.0, delta=TOL)
        self.assertAlmostEqual(t.monthly_bill(600)["energy"], 396 + 2160 + 3006 + 1753, delta=TOL)
        self.assertAlmostEqual(t.monthly_bill(-5)["total"], 130 * 1.16, delta=TOL)

    def test_subsidy_rule(self):
        self.assertEqual(pm_surya_ghar_cfa(1), 30000)
        self.assertEqual(pm_surya_ghar_cfa(2), 60000)
        self.assertEqual(pm_surya_ghar_cfa(3), 78000)
        self.assertEqual(pm_surya_ghar_cfa(5), 78000)
        self.assertEqual(pm_surya_ghar_cfa(2.5), 69000)

    def test_lcc_grid_closed_form(self):
        x = 1.03 / 1.07
        expected = 44070.72 * x * (1 - x ** 25) / (1 - x)
        self.assertAlmostEqual(lcc(self.a, 25, 0.07), expected, delta=TOL)

    def test_lcc_pv_closed_form(self):
        d, e, k = 0.07, 0.03, 0.995
        x = (1 + e) / (1 + d)
        # net import every year stays below 100 kWh/month -> only slab 1 (3.96) + wheeling 1.60
        c = 12 * 1.16
        energy = c * (300 * 5.56 + 130) * x * (1 - x ** 25) / (1 - x) \
            - c * 240 * 5.56 * x * (1 - (k * x) ** 25) / (1 - k * x)
        xo = 1.04 / 1.07
        om = 2000 * xo * (1 - xo ** 25) / (1 - xo)
        inverter = 20000 / d_pow(12) + 20000 / d_pow(24) - 20000 * 11 / 12 / d_pow(25)
        expected = 120000 - 60000 + energy + om + inverter
        self.assertAlmostEqual(lcc(self.b, 25, 0.07), expected, delta=TOL)

    def test_net_import_never_leaves_first_slab(self):
        self.assertLess((self.et["grid_import_B_kwh"] / 12).max(), 100)

    def test_payback_and_breakeven_consistent(self):
        dpb = discounted_payback(self.a, self.b, 25, 0.07)
        self.assertTrue(dpb is not None and 0 < dpb < 25)
        roots = breakeven_discount_rate(self.a, self.b, 25)
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(net_savings(self.a, self.b, 25, roots[0]), 0.0, delta=1.0)

    def test_surplus_case(self):
        big = SolarCase(capacity_kwp=4.0, export_rate=3.0)
        a, b, et = build_alternatives(big)
        self.assertGreater(et["surplus_export_kwh"].iloc[0], 0)
        self.assertEqual(et["grid_import_B_kwh"].iloc[0], 0)
        self.assertTrue(any(i.name == "Surplus export credit" for i in b.items))

    def test_carbon_cost_optional(self):
        c = SolarCase(carbon_price=1000)
        a, b, et = build_alternatives(c)
        pv_a = cashflow_table(a, 25, 0.07)
        carbon = pv_a[pv_a["category"] == "Carbon"]["present_value"].sum()
        self.assertAlmostEqual(carbon, 3600 * 0.727 / 1000 * 1000 * P_A(0.07, 25), delta=TOL)

    def test_tornados_run(self):
        t = tornado_parameters(self.case)
        self.assertEqual(len(t), 9)
        self.assertTrue((t["range"] >= 0).all())
        ti = tornado_items(self.a, self.b, 25, 0.07)
        self.assertGreater(len(ti), 0)

    def test_json_roundtrip(self):
        txt = project_to_json([self.a, self.b], 25, 0.07, "bench")
        alts, n, d, title = project_from_json(txt)
        self.assertAlmostEqual(lcc(alts[1], n, d), lcc(self.b, 25, 0.07), delta=TOL)


def d_pow(t, d=0.07):
    return (1 + d) ** t


if __name__ == "__main__":
    unittest.main()
