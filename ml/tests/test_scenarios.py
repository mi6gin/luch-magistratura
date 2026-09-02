from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.scenarios import SCENARIOS, benchmark_scenarios, generate_scenario
from research.trainer import TrainingConfig


class ScenarioBenchmarkTest(unittest.TestCase):
    def test_generators_create_distinct_controlled_factors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = {}
            for scenario in SCENARIOS:
                data, _ = generate_scenario(scenario, root, series_count=2, days=220)
                generated[scenario] = pd.read_csv(data)
            self.assertGreater(generated["seasonality"].groupby("wday")["sales"].mean().std(), 1)
            self.assertGreater(generated["trend"].tail(60)["sales"].mean(), generated["trend"].head(60)["sales"].mean())
            self.assertGreater(generated["promotion"].loc[generated["promotion"]["snap"] == 1, "sales"].mean(), generated["promotion"].loc[generated["promotion"]["snap"] == 0, "sales"].mean())
            self.assertGreater(generated["external_factors"]["sell_price"].nunique(), 10)

    def test_benchmark_summarizes_accuracy_speed_and_complexity(self):
        counter = 0

        def runner(data, manifest, output, models, config, folds):
            nonlocal counter
            counter += 1
            return {
                "experiment_id": f"EXP-{counter}",
                "results": [{
                    "model": model,
                    "metrics": {"wape_pct": 10 + index},
                    "training_seconds": 2 + index,
                    "parameter_count": 100 + index,
                } for index, model in enumerate(models)],
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = benchmark_scenarios(
                root / "scenarios", root / "experiments", ["lstm", "gru"],
                TrainingConfig(max_epochs=1), series_count=2, days=220, runner=runner,
            )
            self.assertEqual(counter, 4)
            self.assertEqual(result["models"]["lstm"]["scenario_wins"], 4)
            self.assertEqual(result["models"]["lstm"]["training_seconds"], 8)
            self.assertEqual(len(result["scenarios"]), 4)


if __name__ == "__main__":
    unittest.main()
