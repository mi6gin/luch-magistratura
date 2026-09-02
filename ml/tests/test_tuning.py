from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.tuning import trial_grid, tune_models


class HyperparameterTuningTest(unittest.TestCase):
    def test_grid_is_deterministic_and_covers_all_architectures(self):
        models = ["lstm", "gru", "transformer"]
        self.assertEqual(len(trial_grid(models, "smoke")), 3)
        self.assertEqual(len(trial_grid(models, "full")), 24)
        self.assertEqual(trial_grid(models, "full"), trial_grid(models, "full"))

    def test_tuning_selects_by_wape_and_persists_reproducible_summary(self):
        calls = []

        def runner(data, manifest, output, models, config, folds):
            calls.append((models[0], config.hidden_size, folds))
            wape = 20.0 if models[0] == "gru" else 30.0
            return {
                "experiment_id": f"EXP-{len(calls)}",
                "results": [{
                    "model": models[0],
                    "metrics": {"wape_pct": wape},
                    "training_seconds": 2.0,
                    "parameter_count": 100,
                }],
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = tune_models(
                root / "data.csv", root / "manifest.json", root / "experiments", root / "tuning",
                ["lstm", "gru"], runner=runner,
            )
            saved = json.loads((root / "tuning" / result["tuning_id"] / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["winner"]["model"], "gru")
            self.assertEqual(len(calls), 2)
            self.assertEqual(saved["selection_rule"], result["selection_rule"])


if __name__ == "__main__":
    unittest.main()
