from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import torch
except ImportError:
    torch = None

from research.models import build_model, pinball_loss


@unittest.skipIf(torch is None, "PyTorch is installed only in the research environment")
class NeuralArchitectureTest(unittest.TestCase):
    def test_all_architectures_emit_ordered_non_negative_quantiles(self):
        values = torch.rand(2, 14, 8)
        actual = torch.rand(2, 7)
        for name in ("lstm", "gru", "transformer"):
            with self.subTest(model=name):
                model = build_model(name, feature_count=8, history_days=14, horizon_days=7, hidden_size=16)
                prediction = model(values)
                self.assertEqual(tuple(prediction.shape), (2, 7, 3))
                self.assertTrue(torch.all(prediction >= 0))
                self.assertTrue(torch.all(prediction[..., 0] <= prediction[..., 1]))
                self.assertTrue(torch.all(prediction[..., 1] <= prediction[..., 2]))
                self.assertTrue(torch.isfinite(pinball_loss(prediction, actual)))
