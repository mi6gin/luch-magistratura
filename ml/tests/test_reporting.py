from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.reporting import build_research_report


class ResearchReportingTest(unittest.TestCase):
    def test_report_builds_recommendations_tables_and_charts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = {"series_id": "SKU-1", "actual": [1, 2], "q10": [0, 1], "q50": [1, 2], "q90": [2, 3]}
            experiment = {
                "experiment_id": "EXP-1", "dataset": {"dataset": "Example"}, "rolling_folds": 3,
                "results": [
                    {"model": "median", "metrics": {"wape_pct": 8, "wape_pct_std": 1}, "training_seconds": 0, "parameter_count": 0},
                    {"model": "gru", "metrics": {"wape_pct": 10, "wape_pct_std": 2}, "training_seconds": 3, "parameter_count": 20, "forecast_preview": preview},
                ],
            }
            scenarios = {"scenarios": [{"scenario": "trend", "best_neural": "gru", "winner": "gru"}]}
            scalability = {"results": [{
                "series": 10, "rows": 1000, "wall_seconds": 2, "process_peak_memory_mb": 128,
                "models": [{"model": "gru", "training_seconds": 1}],
            }]}
            paths = []
            for name, value in (("experiment", experiment), ("scenarios", scenarios), ("scale", scalability)):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            result = build_research_report(*paths, root / "report")
            self.assertEqual(result["overall_winner"], "median")
            self.assertEqual(result["best_neural"], "gru")
            self.assertTrue((root / "report" / "forecast-gru.svg").is_file())
            self.assertIn("Рекомендации по сценариям", (root / "report" / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
