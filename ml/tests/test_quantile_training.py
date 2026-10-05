import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.models import build_model, pinball_loss, require_torch
from research.trainer import _loader


class QuantileTrainingTest(unittest.TestCase):
    def test_initially_negative_outputs_can_learn_positive_demand(self):
        torch, _ = require_torch()
        for architecture in ['lstm', 'gru', 'transformer']:
            with self.subTest(architecture=architecture):
                model = build_model(architecture, 2, history_days=8, horizon_days=3, hidden_size=8)
                with torch.no_grad():
                    for parameter in model.parameters():
                        parameter.zero_()
                    model.head.bias.fill_(-10)
                prediction = model(torch.zeros(2, 8, 2))
                pinball_loss(prediction, torch.ones(2, 3)).backward()
                self.assertTrue(torch.all(model.head.bias.grad < 0).item())
                self.assertTrue(torch.all(prediction[..., 1:] >= prediction[..., :-1]).item())

    def test_legacy_checkpoint_parameterization_is_preserved(self):
        torch, _ = require_torch()
        model = build_model('gru', 2, 8, 3, 8, 'sorted_clamped_v1')
        with torch.no_grad():
            for parameter in model.parameters():
                parameter.zero_()
            model.head.bias.copy_(torch.tensor([-1., 3., 2.] * 3))
        prediction = model(torch.zeros(1, 8, 2))
        torch.testing.assert_close(prediction, torch.tensor([[[0., 2., 3.]] * 3]))

    def test_seed_controls_reproducible_minibatch_order(self):
        torch, _ = require_torch()
        import numpy as np
        values = (np.arange(40, dtype=np.float32).reshape(20, 2, 1), np.zeros((20, 1), dtype=np.float32), ['s'] * 20)
        def order(seed):
            return torch.cat([batch[0][:, 0, 0] for batch in _loader(values, 4, True, seed)])
        torch.testing.assert_close(order(42), order(42))
        self.assertFalse(torch.equal(order(42), order(43)))


if __name__ == '__main__':
    unittest.main()
