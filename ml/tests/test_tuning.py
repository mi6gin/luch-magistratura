from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.tuning import trial_grid, tune_models
from research.experiment import _fold_manifest, run_experiment
from research.trainer import TrainingConfig


class HyperparameterTuningTest(unittest.TestCase):
    def test_grid_is_deterministic_and_covers_all_architectures(self):
        models = ["lstm", "gru", "transformer"]
        self.assertEqual(len(trial_grid(models, "smoke")), 3)
        self.assertEqual(len(trial_grid(models, "full")), 24)
        self.assertEqual(trial_grid(models, "full"), trial_grid(models, "full"))

    def test_custom_boundaries_preserve_reserved_test_and_separate_rolling_tests(self):
        manifest = {
            "date_start": "2020-01-01", "train_end": "2021-09-30",
            "validation_end": "2021-10-31", "test_end": "2021-12-31",
        }
        final = _fold_manifest(manifest, 0, 1)
        self.assertEqual(final, manifest)
        folds = [_fold_manifest(manifest, index, 3) for index in range(3)]
        self.assertEqual(folds[-1], manifest)
        for fold in folds:
            self.assertEqual((pd.Timestamp(fold["validation_end"]) - pd.Timestamp(fold["train_end"])).days, 31)
            self.assertEqual((pd.Timestamp(fold["test_end"]) - pd.Timestamp(fold["validation_end"])).days, 61)
        for earlier, later in zip(folds, folds[1:]):
            self.assertLessEqual(earlier["test_end"], later["validation_end"])
        for index in range(3):
            tuning_fold = _fold_manifest(manifest, index, 3, evaluation_split="validation")
            self.assertLessEqual(tuning_fold["validation_end"], manifest["validation_end"])
            self.assertEqual(tuning_fold["test_end"], manifest["test_end"])

    def test_tuning_uses_validation_even_when_test_ranking_is_opposite(self):
        calls = []

        def runner(data, manifest, output, models, config, folds, evaluation_split="test"):
            calls.append((models[0], config.hidden_size, folds, evaluation_split))
            ranking = {"validation": {"gru": 20, "lstm": 30}, "test": {"gru": 30, "lstm": 20}}
            wape = ranking[evaluation_split][models[0]]
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
            self.assertTrue(all(call[-1] == "validation" for call in calls))
            self.assertEqual(saved["evaluation_split"], "validation")
            self.assertFalse(saved["test_evaluated"])
            self.assertEqual(saved["selection_rule"], result["selection_rule"])

    def test_validation_experiment_never_evaluates_reserved_test_in_rolling_folds(self):
        dates = pd.date_range("2024-01-01", periods=360)
        train_end, validation_end = dates[-85], dates[-29]
        frame = pd.DataFrame({
            "date": dates, "id": "sku", "sales": np.where(dates > validation_end, 9999, 1),
            "sell_price": 1, "wday": dates.dayofweek + 1, "month": dates.month,
            "is_event": 0, "snap": 0,
        })
        manifest = {
            "dataset": "Reserved test regression", "date_start": str(dates[0].date()),
            "train_end": str(train_end.date()), "validation_end": str(validation_end.date()),
            "test_end": str(dates[-1].date()),
        }
        evaluated = []

        def fake_train(name, train, validation, output, config):
            self.assertTrue(np.all(train[1] == 1))
            self.assertTrue(np.all(validation[1] == 1))
            return {"model": name, "weights": "fake.pt", "training_seconds": 0, "parameter_count": 1}

        def fake_evaluate(name, path, values, scales):
            evaluated.append(values)
            self.assertTrue(np.all(values[1] == 1))
            return {"wape_pct": 0, "test_windows": len(values[1])}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame.to_csv(root / "data.csv", index=False)
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch("research.experiment.train_model", side_effect=fake_train), \
                 patch("research.experiment.evaluate_model", side_effect=fake_evaluate), \
                 patch.dict(sys.modules, {"torch": SimpleNamespace(__version__="test-double")}):
                result = run_experiment(
                    root / "data.csv", root / "manifest.json", root / "output", ["gru"],
                    TrainingConfig(history_days=14, horizon_days=7), folds=3, evaluation_split="validation",
                )
            self.assertEqual(len(evaluated), 3)
            self.assertFalse(result["reserved_test_period"]["evaluated"])
            self.assertEqual(result["folds"][-1]["train_end"], manifest["train_end"])
            self.assertEqual(result["folds"][-1]["evaluation_end"], manifest["validation_end"])
            self.assertTrue(all(fold["evaluation_end"] <= manifest["validation_end"] for fold in result["folds"]))
            for fold in result["folds"]:
                for item in fold["results"]:
                    self.assertEqual(item["metrics"]["evaluation_split"], "validation")
                    self.assertNotIn("test_windows", item["metrics"])
            final = run_experiment(
                root / "data.csv", root / "manifest.json", root / "output", [],
                TrainingConfig(history_days=14, horizon_days=7),
            )
            self.assertEqual(final["evaluation_split"], "test")
            self.assertTrue(final["reserved_test_period"]["evaluated"])
            baseline = final["folds"][0]["results"][0]["metrics"]
            self.assertGreater(baseline["wape_pct"], 0)
            self.assertGreater(baseline["test_windows"], 0)

    def test_tuning_requires_a_model(self):
        with self.assertRaisesRegex(ValueError, "хотя бы одну модель"):
            tune_models(Path("unused"), Path("unused"), Path("unused"), Path("unused"), [])


if __name__ == "__main__":
    unittest.main()
