from __future__ import annotations

import numpy as np


def point_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = predicted - actual
    denominator = max(float(np.abs(actual).sum()), 1e-9)
    return {
        "wape_pct": round(float(np.abs(error).sum() / denominator * 100), 4),
        "mae": round(float(np.abs(error).mean()), 4),
        "rmse": round(float(np.sqrt(np.mean(error**2))), 4),
        "bias_pct": round(float(error.sum() / denominator * 100), 4),
    }


def interval_coverage(actual: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    return round(float(np.mean((actual >= lower) & (actual <= upper)) * 100), 4)


def quantiles_are_ordered(values: np.ndarray) -> bool:
    values = np.asarray(values, dtype=float)
    return bool(np.all(values[..., 0] <= values[..., 1]) and np.all(values[..., 1] <= values[..., 2]))

