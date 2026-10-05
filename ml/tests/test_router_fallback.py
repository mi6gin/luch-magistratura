from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.dataset import FEATURES
from research.experiment import adaptive_baseline, risk_calibrated_baseline


class RouterFallbackTest(unittest.TestCase):
    def test_new_demand_class_uses_median_and_exports_the_same_fallback_route(self):
        calibration_history = np.zeros((1, 90, len(FEATURES)), dtype=np.float32)
        calibration_history[:, :, 0] = 10
        calibration = (calibration_history, np.full((1, 7), 10, dtype=np.float32), ["sku"])
        test_history = np.zeros_like(calibration_history)
        test_history[:, ::2, 0] = 8  # Intermittent class is absent from calibration.
        test = (test_history, np.full((1, 7), 4, dtype=np.float32), ["sku"])
        for router, fallback_route in (
            (adaptive_baseline, "moving_median_28"),
            (risk_calibrated_baseline, "moving_median_28 × 1"),
        ):
            with self.subTest(router=router.__name__):
                result = router(calibration, test, {"sku": 1})
                self.assertEqual(result["metrics"]["wape_pct"], 0)
                self.assertEqual(result["metrics"]["underforecast_pct"], 0)
                self.assertEqual(result["routes"]["intermittent"], fallback_route)
                self.assertEqual(set(result["routes"]), {"smooth", "intermittent", "erratic", "lumpy"})


if __name__ == "__main__":
    unittest.main()
