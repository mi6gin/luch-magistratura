from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

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


def run_experiment(data_path: Path, manifest_path: Path, output_root: Path, models: list[str], config: TrainingConfig) -> dict:
    import torch

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _, scales, train, validation, test = load_experiment_data(str(data_path), manifest, config.history_days, config.horizon_days)
    experiment_id = datetime.now(timezone.utc).strftime("EXP-%Y%m%dT%H%M%SZ")
    output_dir = output_root / experiment_id
    results = [seasonal_baseline(test, scales.sales)]
    for name in models:
        training = train_model(name, train, validation, output_dir, config)
        metrics = evaluate_model(name, output_dir / training["weights"], test, scales.sales)
        results.append({**training, "metrics": metrics})
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
        "champion": ranked[0]["model"],
        "ranking": [item["model"] for item in ranked],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    save_result(output_dir / "result.json", document)
    return document
