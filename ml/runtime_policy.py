"""Apply a validated, explainable local demand-routing production artifact."""

from __future__ import annotations

import json
import math
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


def load_active_policy(registry_path: str | os.PathLike[str] | None = None) -> tuple[dict | None, str | None]:
    registry = registry_path or os.getenv("ML_MODEL_REGISTRY_PATH")
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


def apply_active_policy(
    history,
    projection: dict[str, np.ndarray],
    *,
    reference_level: float | None = None,
    dates=None,
    sanity_cap: float | None = None,
) -> tuple[dict[str, np.ndarray], str, str | None]:
    """Calibrate the demand level while retaining calendar and scenario effects.

    The reference is the mean neutral seasonal profile, before price, events,
    or strategy-specific trend. Using the scenario median as that denominator
    would cancel those effects, making simulations identical to the base case.
    Scaling all quantiles also retains their relative uncertainty and ordering.
    """
    artifact, warning = load_active_policy()
    if artifact is None:
        return projection, "seasonal-robust-v1", warning
    if "sale_date" in history:
        history = history.sort_values("sale_date", kind="stable")
    demand = np.asarray(history["recovered_demand"].tail(90), dtype=float)
    label = _demand_type(demand)
    route = artifact["routes"].get(label)
    match = METHOD_PATTERN.fullmatch(str(route or ""))
    if not match:
        return projection, "seasonal-robust-v1", "Для типа спроса нет корректного route; использован безопасный baseline."
    method, multiplier_value = match.groups()
    multiplier = float(multiplier_value or 1)
    if not math.isfinite(multiplier):
        return projection, "seasonal-robust-v1", "Некорректный multiplier; использован безопасный baseline."
    horizon = len(projection["q50"])
    if method == "seasonal_naive_7" and len(demand) >= 7:
        if dates is not None and "sale_date" in history:
            last_weekdays = history.groupby(history["sale_date"].dt.dayofweek)["recovered_demand"].last()
            median = np.asarray([last_weekdays.get(date.dayofweek, np.median(demand[-7:])) for date in dates])
        else:
            median = demand[-7:][np.arange(horizon) % 7]
    elif method == "croston_sba":
        median = np.repeat(_croston_sba(demand), horizon)
    else:
        median = np.repeat(float(np.median(demand[-28:])) if len(demand) else 0.0, horizon)
    neutral = float(reference_level) if reference_level is not None else float(np.mean(projection["q50"]))
    if not len(demand) or not math.isfinite(neutral) or neutral <= 0 or not horizon:
        return projection, "seasonal-robust-v1", "Недостаточно спроса для калибровки; использован безопасный baseline."
    scale = max(float(np.mean(median)) * multiplier / neutral, 0.0)
    if not math.isfinite(scale):
        return projection, "seasonal-robust-v1", "Некорректная калибровка; использован безопасный baseline."
    cap = float(sanity_cap) if sanity_cap is not None else np.inf
    calibrated = {name: np.clip(np.asarray(values) * scale, 0.0, cap) for name, values in projection.items()}
    return calibrated, POLICY_RUNTIME, None
