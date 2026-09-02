"""Apply a validated, explainable local demand-routing production artifact."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np


POLICY_RUNTIME = "local-demand-router-v1"
METHOD_PATTERN = re.compile(r"^(seasonal_naive_7|moving_median_28|croston_sba)(?: × ([0-9]+(?:\.[0-9]+)?|\.[0-9]+))?$")


def _demand_type(history: np.ndarray) -> str:
    positive = history[history > 0]
    if not len(positive):
        return "intermittent"
    adi = len(history) / len(positive)
    cv_squared = float((positive.std() / max(positive.mean(), 1e-9)) ** 2)
    if adi < 1.32 and cv_squared < 0.49:
        return "smooth"
    if adi >= 1.32 and cv_squared < 0.49:
        return "intermittent"
    return "erratic" if adi < 1.32 else "lumpy"


def _croston_sba(history: np.ndarray, alpha: float = 0.1) -> float:
    nonzero = np.flatnonzero(history > 0)
    if not len(nonzero):
        return 0.0
    demand, interval, previous = float(history[nonzero[0]]), float(nonzero[0] + 1), int(nonzero[0])
    for index in nonzero[1:]:
        demand += alpha * (float(history[index]) - demand)
        interval += alpha * (int(index) - previous - interval)
        previous = int(index)
    return max((1 - alpha / 2) * demand / max(interval, 1e-9), 0.0)


def load_active_policy() -> tuple[dict | None, str | None]:
    registry = os.getenv("ML_MODEL_REGISTRY_PATH")
    if not registry or not Path(registry).is_file():
        return None, None
    try:
        state = json.loads(Path(registry).read_text(encoding="utf-8"))
        production = next(item for item in state["models"] if item["id"] == state["production_id"])
        if production.get("name") != POLICY_RUNTIME or production.get("status") != "production":
            return None, None
        artifact_path = Path(production["artifact_path"]).resolve()
        models_root = os.getenv("ML_MODELS_PATH")
        if models_root and not artifact_path.is_relative_to(Path(models_root).resolve()):
            raise ValueError("artifact outside models directory")
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("runtime") != POLICY_RUNTIME or not isinstance(artifact.get("routes"), dict):
            raise ValueError("invalid policy artifact")
        return artifact, None
    except (OSError, KeyError, TypeError, ValueError, StopIteration, json.JSONDecodeError):
        return None, "Production policy недоступна; использован безопасный baseline."


def apply_active_policy(history, projection: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], str, str | None]:
    artifact, warning = load_active_policy()
    if artifact is None:
        return projection, "seasonal-robust-v1", warning
    demand = np.asarray(history["recovered_demand"].tail(90), dtype=float)
    label = _demand_type(demand)
    route = artifact["routes"].get(label)
    match = METHOD_PATTERN.fullmatch(str(route or ""))
    if not match:
        return projection, "seasonal-robust-v1", "Для типа спроса нет корректного route; использован безопасный baseline."
    method, multiplier_value = match.groups()
    multiplier = float(multiplier_value or 1)
    horizon = len(projection["q50"])
    if method == "seasonal_naive_7" and len(demand) >= 7:
        median = demand[-7:][np.arange(horizon) % 7]
    elif method == "croston_sba":
        median = np.repeat(_croston_sba(demand), horizon)
    else:
        median = np.repeat(float(np.median(demand[-28:])) if len(demand) else 0.0, horizon)
    median = np.maximum(median * multiplier, 0)
    lower_gap = np.maximum(projection["q50"] - projection["q10"], 0)
    upper_gap = np.maximum(projection["q90"] - projection["q50"], 0)
    calibrated = {"q10": np.maximum(median - lower_gap, 0), "q50": median, "q90": median + upper_gap}
    return calibrated, POLICY_RUNTIME, None
