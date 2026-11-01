"""Causality and physical accounting checks for the dissertation experiment."""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from ml.research.dataset import FEATURES, normalize_from_train
from ml.research.external_validation import baseline_predictions, simulate_series, window_at
from ml.research.verify_external_validation import verify


class ExternalValidationTests(unittest.TestCase):
    def test_published_evidence_metrics_and_stock_movements_recompute(self):
        result = verify(Path(__file__).resolve().parents[2] / "docs/research/external-validation")
        self.assertEqual(result["status"], "PASS")

    def frame(self):
        dates = pd.date_range("2015-01-01", periods=160)
        return pd.DataFrame({"id": "A", "date": dates, "sales": np.arange(160) % 7,
                             "sell_price": 2., "wday": dates.dayofweek + 1, "month": dates.month,
                             "is_event": 0, "snap": 0})

    def test_neural_inputs_and_scaling_ignore_future_sales_and_prices(self):
        original = self.frame()
        changed = original.copy()
        cutoff = original.date.iloc[120]
        changed.loc[changed.date >= cutoff, ["sales", "sell_price"]] = 999999
        left, left_scales = normalize_from_train(original, "2015-03-31")
        right, right_scales = normalize_from_train(changed, "2015-03-31")
        self.assertEqual(left_scales, right_scales)
        np.testing.assert_array_equal(window_at(left, cutoff, 90), window_at(right, cutoff, 90))

    def test_all_production_baselines_ignore_future_rows(self):
        original = self.frame()
        changed = original.copy()
        cutoff = original.date.iloc[120]
        changed.loc[changed.date >= cutoff, "sales"] = 999999
        before = baseline_predictions(original, cutoff, 28)
        after = baseline_predictions(changed, cutoff, 28)
        for method in before:
            np.testing.assert_array_equal(before[method], after[method])

    def test_receipts_arrive_after_lead_time_not_on_order_day(self):
        result, daily = simulate_series([10, 10, 10, 10], np.full((4, 28), 10.), 0, 2, 1, 0, "2016-01-01")
        self.assertEqual(daily[0][0], 0)
        self.assertEqual(daily[1][0], 0)
        self.assertGreater(daily[2][0], 0)
        self.assertEqual(result["lost"], 20)
        self.assertEqual(result["served"], 20)

    def test_mass_balance_including_outstanding_orders_and_no_future_demand_leak(self):
        forecasts = np.full((8, 28), 3.)
        first, daily_first = simulate_series([1] * 8, forecasts, 4, 3, 1, 0, "2016-01-01")
        second, daily_second = simulate_series([1] * 7 + [100], forecasts, 4, 3, 1, 0, "2016-01-01")
        self.assertEqual(daily_first[:7], daily_second[:7])
        self.assertEqual(daily_first[-1][1], daily_second[-1][1])
        for result in (first, second):
            self.assertAlmostEqual(result["initial_stock"] + result["received"], result["served"] + result["ending_stock"])
            self.assertAlmostEqual(result["ordered"], result["received"] + result["ending_in_transit"])
            self.assertAlmostEqual(result["demand"], result["served"] + result["lost"])

    def test_zero_demand_does_not_create_order(self):
        result, _ = simulate_series(np.zeros(5), np.zeros((5, 28)), 0, 1, 1, 0, "2016-01-01")
        self.assertEqual(result["ordered"], 0)
        self.assertEqual(result["ending_stock"], 0)

    def test_invalid_or_short_forecasts_are_rejected(self):
        for forecasts in (np.full((3, 28), np.nan), np.full((3, 28), -1), np.zeros((3, 1))):
            with self.assertRaises(ValueError):
                simulate_series([1, 1, 1], forecasts, 0, 3, 7, 0, "2016-01-01")


if __name__ == "__main__":
    unittest.main()
