from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime_model import FALLBACK_MODEL, resolve_runtime_model
from runtime_policy import apply_active_policy


class RuntimeModelTest(unittest.TestCase):
    def test_supported_production_model_is_resolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(json.dumps({
                "production_id": "built-in",
                "models": [{"id": "built-in", "name": FALLBACK_MODEL, "status": "production"}],
            }), encoding="utf-8")
            self.assertEqual(resolve_runtime_model(path), (FALLBACK_MODEL, None))

    def test_incompatible_model_falls_back_with_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(json.dumps({
                "production_id": "unsafe",
                "models": [{"id": "unsafe", "name": "research-gru", "status": "production"}],
            }), encoding="utf-8")
            model, warning = resolve_runtime_model(path)
            self.assertEqual(model, FALLBACK_MODEL)
            self.assertIsNotNone(warning)

    def test_local_policy_changes_median_and_preserves_quantile_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "models/policy/manifest.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(json.dumps({
                "runtime": "local-demand-router-v1",
                "routes": {"smooth": "moving_median_28 × 1.5"},
            }), encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({
                "production_id": "policy",
                "models": [{
                    "id": "policy", "name": "local-demand-router-v1", "status": "production",
                    "artifact_path": str(artifact),
                }],
            }), encoding="utf-8")
            history = pd.DataFrame({"recovered_demand": np.repeat(10.0, 90)})
            baseline = {"q10": np.repeat(8.0, 30), "q50": np.repeat(10.0, 30), "q90": np.repeat(13.0, 30)}
            with patch.dict("os.environ", {"ML_MODEL_REGISTRY_PATH": str(registry), "ML_MODELS_PATH": str(root / "models")}):
                result, model, warning = apply_active_policy(history, baseline)
            self.assertEqual(model, "local-demand-router-v1")
            self.assertIsNone(warning)
            self.assertTrue(np.all(result["q50"] == 15))
            self.assertTrue(np.all(result["q10"] <= result["q50"]))
            self.assertTrue(np.all(result["q50"] <= result["q90"]))


if __name__ == "__main__":
    unittest.main()
