from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime_model import FALLBACK_MODEL, resolve_runtime_model


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


if __name__ == "__main__":
    unittest.main()
