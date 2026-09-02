from __future__ import annotations

import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .dataset import load_experiment_data
from .metrics import point_metrics
from .trainer import TrainingConfig, evaluate_model, save_result, train_model


def seasonal_baseline(test, sales_scales: dict[str, float]) -> dict:
    x, y, ids = test
    if x.shape[1] < 7:
        raise ValueError("Seasonal baseline требует минимум 7 дней истории.")
    horizon = y.shape[1]
    prediction = x[:, -7:, 0][:, np.arange(horizon) % 7]
    scales = np.asarray([sales_scales[series_id] for series_id in ids], dtype=float)[:, None]
    return {
        "model": "seasonal_naive_7",
        "metrics": {**point_metrics(y * scales, prediction * scales), "test_windows": len(y)},
        "training_seconds": 0.0,
        "parameter_count": 0,
    }


def _fold_manifest(base: dict, fold_index: int, fold_count: int, step_days: int = 28) -> dict:
    offset = (fold_count - fold_index - 1) * step_days
    test_end = pd.Timestamp(base["test_end"]) - pd.Timedelta(days=offset)
    validation_end = test_end - pd.Timedelta(days=28)
    train_end = validation_end - pd.Timedelta(days=56)
    if train_end <= pd.Timestamp(base["date_start"]) + pd.Timedelta(days=120):
        raise ValueError("Для выбранного числа rolling-окон недостаточно истории.")
    return {
        **base,
        "train_end": train_end.date().isoformat(),
        "validation_end": validation_end.date().isoformat(),
        "test_end": test_end.date().isoformat(),
    }


def _aggregate(results: list[dict]) -> list[dict]:
    model_names = [item["model"] for item in results[0]]
    aggregated = []
    for name in model_names:
        folds = [next(item for item in result if item["model"] == name) for result in results]
        metric_names = ["wape_pct", "mae", "rmse", "bias_pct"]
        metrics = {}
        for metric in metric_names:
            values = np.asarray([fold["metrics"][metric] for fold in folds], dtype=float)
            metrics[metric] = round(float(values.mean()), 4)
            metrics[f"{metric}_std"] = round(float(values.std(ddof=1)), 4) if len(values) > 1 else 0.0
        coverage_values = [fold["metrics"].get("coverage_pct") for fold in folds if "coverage_pct" in fold["metrics"]]
        if coverage_values:
            metrics["coverage_pct"] = round(float(np.mean(coverage_values)), 4)
            metrics["coverage_pct_std"] = round(float(np.std(coverage_values, ddof=1)), 4) if len(coverage_values) > 1 else 0.0
        aggregated.append({
            "model": name,
            "metrics": metrics,
            "training_seconds": round(sum(float(fold.get("training_seconds", 0)) for fold in folds), 3),
            "parameter_count": int(folds[-1].get("parameter_count", 0)),
            "folds_completed": len(folds),
        })
    return aggregated


def run_experiment(
    data_path: Path,
    manifest_path: Path,
    output_root: Path,
    models: list[str],
    config: TrainingConfig,
    folds: int = 1,
) -> dict:
    import torch

    if folds < 1 or folds > 6:
        raise ValueError("Количество rolling-окон должно быть от 1 до 6.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    experiment_id = datetime.now(timezone.utc).strftime("EXP-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6].upper()
    output_dir = output_root / experiment_id
    fold_documents = []
    fold_results = []
    for fold_index in range(folds):
        current_manifest = _fold_manifest(manifest, fold_index, folds)
        _, scales, train, validation, test = load_experiment_data(str(data_path), current_manifest, config.history_days, config.horizon_days)
        current_results = [seasonal_baseline(test, scales.sales)]
        fold_dir = output_dir / f"fold-{fold_index + 1}"
        for name in models:
            print(f"fold {fold_index + 1}/{folds}: training {name}", file=sys.stderr, flush=True)
            training = train_model(name, train, validation, fold_dir, config)
            metrics = evaluate_model(name, fold_dir / training["weights"], test, scales.sales)
            current_results.append({**training, "metrics": metrics})
        fold_results.append(current_results)
        fold_documents.append({
            "fold": fold_index + 1,
            "train_end": current_manifest["train_end"],
            "validation_end": current_manifest["validation_end"],
            "test_end": current_manifest["test_end"],
            "results": current_results,
        })
    results = _aggregate(fold_results)
    ranked = sorted(results, key=lambda item: item["metrics"]["wape_pct"])
    document = {
        "experiment_id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": manifest,
        "config": config.__dict__,
        "environment": {
            "python": sys.version.split()[0],
            "pytorch": torch.__version__,
            "platform": platform.platform(),
        },
        "results": results,
        "folds": fold_documents,
        "rolling_folds": folds,
        "champion": ranked[0]["model"],
        "ranking": [item["model"] for item in ranked],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    save_result(output_dir / "result.json", document)
    return document
