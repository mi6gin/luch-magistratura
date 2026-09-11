import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecasting import _quality_warnings, _recommendation_reasons, evaluate_baseline


class ForecastQualityTest(unittest.TestCase):
    def test_holdout_compares_model_with_weekly_naive_baseline(self):
        dates = pd.date_range("2026-01-01", periods=140, freq="D")
        demand = np.asarray([12 + date.dayofweek * 2 + (index % 3) for index, date in enumerate(dates)], dtype=float)
        sales = pd.DataFrame({
            "product_id": 1,
            "sale_date": dates,
            "quantity_sold": demand,
            "recovered_demand": demand,
            "in_stock": True,
            "is_promo": False,
            "is_holiday": False,
            "was_oos_recovered": False,
        })

        result = evaluate_baseline({"sales": sales}, holdout_days=28)

        self.assertEqual(result["comparison"]["baseline_model"], "seasonal-naive-weekly")
        self.assertGreaterEqual(result["comparison"]["baseline_wape_pct"], 0)
        self.assertIn(result["comparison"]["verdict"], {"better", "equal", "worse"})
        self.assertEqual(
            result["comparison"]["wape_improvement_pct"],
            round(result["comparison"]["baseline_wape_pct"] - result["wape_pct"], 2),
        )

    def test_product_quality_warnings_and_reasons_are_explainable(self):
        warnings = _quality_warnings({
            "history_days": 30,
            "completeness_pct": 70,
            "oos_rate_pct": 20,
            "staleness_days": 12,
        })
        self.assertEqual(len(warnings), 4)

        reasons = _recommendation_reasons(
            order_quantity=18,
            stockout="2026-09-20",
            selected_quantile="q90",
            lead_time=7,
            available=42,
            lead_demand=60,
            quality={"score": 74},
        )
        self.assertTrue(any("q90" in reason for reason in reasons))
        self.assertTrue(any("дефицит" in reason for reason in reasons))
        self.assertTrue(any("18" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
