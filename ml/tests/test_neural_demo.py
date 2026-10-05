import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import numpy as np

from ml.research.dataset import FEATURES
from ml.research.demo import predict
from ml.research.models import build_model, require_torch
from ml.research.trainer import TrainingConfig


class NeuralDemoTests(unittest.TestCase):
    def test_saved_prototypes_predict_ordered_quantiles_and_preserve_scale(self):
        torch, _ = require_torch()
        torch.set_num_threads(2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = {"features": list(FEATURES), "normalized_history": np.ones((7, len(FEATURES))).tolist(),
                       "sales_scale": 10, "series_id": "public-sku", "source": "UCI",
                       "forecast_start": "2011-11-12"}
            (root / "example.json").write_text(json.dumps(example), encoding="utf-8")
            config = TrainingConfig(history_days=7, horizon_days=3, hidden_size=8)
            for name in ("lstm", "gru", "transformer"):
                with self.subTest(model=name):
                    model = build_model(name, len(FEATURES), 7, 3, 8)
                    for parameter in model.parameters():
                        torch.nn.init.zeros_(parameter)
                    checkpoint = root / f"{name}.pt"
                    torch.save({"model": name, "state_dict": model.state_dict(), "config": asdict(config),
                                "feature_count": len(FEATURES), "quantile_parameterization": "softplus_increments_v2"}, checkpoint)
                    forecast = predict(checkpoint, root / "example.json")
                    self.assertEqual(len(forecast["q50"]), 3)
                    np.testing.assert_allclose(forecast["q10"], 10 * np.log(2), rtol=1e-6)
                    np.testing.assert_allclose(forecast["q50"], 20 * np.log(2), rtol=1e-6)
                    np.testing.assert_allclose(forecast["q90"], 30 * np.log(2), rtol=1e-6)
                    example["features"] = list(reversed(FEATURES))
                    (root / "invalid.json").write_text(json.dumps(example), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Feature order"):
                        predict(checkpoint, root / "invalid.json")
                    example["features"] = list(FEATURES)


if __name__ == "__main__":
    unittest.main()
