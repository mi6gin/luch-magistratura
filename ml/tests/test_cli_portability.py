from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT))

from research.scalability import _peak_memory_mb, benchmark_scalability
from research.trainer import TrainingConfig


class CliPortabilityTest(unittest.TestCase):
    def test_cli_help_does_not_require_unix_resource_module(self):
        script = """
import builtins
import runpy
import sys
original_import = builtins.__import__
def portable_import(name, *args, **kwargs):
    if name == 'resource':
        raise ModuleNotFoundError('resource is unavailable on Windows')
    return original_import(name, *args, **kwargs)
builtins.__import__ = portable_import
sys.argv = ['research_cli.py', '--help']
runpy.run_path('research_cli.py', run_name='__main__')
"""
        completed = subprocess.run([sys.executable, "-c", script], cwd=ML_ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("prepare-local", completed.stdout)
        self.assertIn("scale", completed.stdout)

    def test_native_process_peak_is_available_on_supported_platforms(self):
        if sys.platform not in ("win32", "linux", "darwin"):
            self.skipTest("No supported process-memory backend on this platform")
        self.assertGreater(_peak_memory_mb(), 0)

    def test_full_research_json_is_utf8_under_windows_legacy_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dates = pd.date_range("2024-01-01", periods=360)
            data_path, manifest_path = root / "data.csv", root / "manifest.json"
            pd.DataFrame({
                "date": dates, "id": "sku", "sales": 2, "sell_price": 1,
                "wday": dates.dayofweek + 1, "month": dates.month, "is_event": 0, "snap": 0,
            }).to_csv(data_path, index=False)
            manifest_path.write_text(json.dumps({
                "dataset": "Encoding regression × 東京", "date_start": str(dates[0].date()),
                "train_end": str(dates[-85].date()), "validation_end": str(dates[-29].date()),
                "test_end": str(dates[-1].date()),
            }), encoding="utf-8")
            environment = {**os.environ, "PYTHONIOENCODING": "cp1251"}
            completed = subprocess.run([
                sys.executable, str(ML_ROOT / "research_cli.py"), "train",
                "--data", str(data_path), "--manifest", str(manifest_path),
                "--output", str(root / "experiments"), "--models", "--folds", "1",
            ], env=environment, capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
            document = json.loads(completed.stdout.decode("utf-8"))
            self.assertEqual(document["dataset"]["dataset"], "Encoding regression × 東京")
            risk_router = next(item for item in document["results"] if item["model"] == "risk_calibrated_router")
            self.assertTrue(any("×" in route for route in risk_router["routes"].values()))

    def test_scalability_records_cumulative_memory_scope_and_unavailable_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "data.csv"
            manifest_path = root / "manifest.json"
            pd.DataFrame({"id": ["sku"] * 190, "date": pd.date_range("2024-01-01", periods=190)}).to_csv(data_path, index=False)
            preprocessing = {"target_censoring": "exclude_forecast_windows_containing_explicit_stockouts"}
            manifest_path.write_text(json.dumps({"dataset": "Test", "source": "fixture", "preprocessing": preprocessing}), encoding="utf-8")
            result = {"model": "gru", "metrics": {"wape_pct": 1, "inference_ms": 2}, "training_seconds": 3, "parameter_count": 4}
            experiment = {"experiment_id": "fixture", "folds": [{"results": [result]}], "results": [result]}
            with patch("research.scalability.run_experiment", return_value=experiment), patch("research.scalability._peak_memory_mb", return_value=None):
                document = benchmark_scalability(data_path, manifest_path, root / "scale", root / "experiments", ["gru"], [1], TrainingConfig())
            self.assertIsNone(document["results"][0]["process_peak_memory_mb"])
            measurement = document["memory_measurement"]
            self.assertEqual(measurement["scope"], "process_lifetime_high_water_mark")
            self.assertTrue(measurement["shared_process"])
            self.assertFalse(measurement["independent_per_size"])
            subset_manifest = json.loads((root / "scale" / document["benchmark_id"] / "data/series-1.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(subset_manifest["preprocessing"], preprocessing)


if __name__ == "__main__":
    unittest.main()
