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


def demand_type(history: np.ndarray) -> str:
    history = np.asarray(history, dtype=float)
    positive = history[history > 0]
    if not len(positive):
        return "intermittent"
    adi = len(history) / len(positive)
    cv_squared = float((positive.std() / max(positive.mean(), 1e-9)) ** 2)
    if adi < 1.32 and cv_squared < 0.49:
        return "smooth"
    if adi >= 1.32 and cv_squared < 0.49:
        return "intermittent"
    if adi < 1.32:
        return "erratic"
    return "lumpy"


def segment_metrics(actual: np.ndarray, predicted: np.ndarray, histories: np.ndarray) -> dict[str, dict[str, float]]:
    labels = np.asarray([demand_type(history) for history in histories])
    return {
        label: {**point_metrics(actual[labels == label], predicted[labels == label]), "windows": int((labels == label).sum())}
        for label in ("smooth", "intermittent", "erratic", "lumpy")
        if np.any(labels == label)
    }
