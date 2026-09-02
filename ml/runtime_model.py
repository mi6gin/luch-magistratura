"""Resolve the production model conservatively and fall back to the built-in engine."""

from __future__ import annotations

import json
import os
from pathlib import Path


FALLBACK_MODEL = "seasonal-robust-v1"
SUPPORTED_MODELS = {FALLBACK_MODEL}


def resolve_runtime_model(path: str | os.PathLike[str] | None = None) -> tuple[str, str | None]:
    configured = path or os.getenv("ML_MODEL_REGISTRY_PATH")
    if not configured:
        return FALLBACK_MODEL, None
    registry_path = Path(configured).expanduser()
    if not registry_path.is_file():
        return FALLBACK_MODEL, None
    try:
        state = json.loads(registry_path.read_text(encoding="utf-8"))
        production_id = state.get("production_id")
        production = next(item for item in state.get("models", []) if item.get("id") == production_id)
        name = str(production.get("name", ""))
        if production.get("status") != "production" or name not in SUPPORTED_MODELS:
            raise ValueError("production model is not supported")
        return name, None
    except (OSError, ValueError, TypeError, json.JSONDecodeError, StopIteration):
        return FALLBACK_MODEL, "Реестр моделей недоступен или несовместим; использован безопасный baseline."
