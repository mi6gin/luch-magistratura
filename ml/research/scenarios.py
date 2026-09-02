from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .data import DatasetManifest, temporal_boundaries
from .experiment import run_experiment
from .trainer import TrainingConfig


SCENARIOS = ("seasonality", "trend", "promotion", "external_factors")


def generate_scenario(name: str, output_dir: Path, series_count: int = 12, days: int = 360, seed: int = 42) -> tuple[Path, Path]:
    if name not in SCENARIOS:
        raise ValueError(f"Неизвестный сценарий: {name}")
    if days < 220 or series_count < 1:
        raise ValueError("Сценарию требуется минимум 220 дней и один временной ряд.")
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    rows = []
    for series in range(series_count):
        scale = 12 + series * 0.8
        time_index = np.arange(days, dtype=float)
        price = np.full(days, 100 + series * 3, dtype=float)
        event = np.zeros(days, dtype=int)
        promo = np.zeros(days, dtype=int)
        if name == "seasonality":
            mean = scale * (1 + 0.45 * np.sin(2 * np.pi * time_index / 7) + 0.2 * np.sin(2 * np.pi * time_index / 30))
        elif name == "trend":
            mean = scale * (0.65 + 0.9 * time_index / days)
        elif name == "promotion":
            promo[(time_index.astype(int) % 28) < 4] = 1
            mean = scale * np.where(promo, 2.2, 1.0)
        else:
            price = (100 + series * 3) * (1 + 0.12 * np.sin(2 * np.pi * time_index / 45))
            event[(time_index.astype(int) % 60) == 0] = 1
            mean = scale * (price / np.median(price)) ** -1.4 * np.where(event, 2.0, 1.0)
        demand = rng.poisson(np.maximum(mean, 0.1)).astype(float)
        rows.extend({
            "date": date,
            "id": f"scenario-{series + 1}",
            "sales": demand[index],
            "sell_price": price[index],
            "wday": date.dayofweek + 1,
            "month": date.month,
            "year": date.year,
            "is_event": int(event[index]),
            "snap": int(promo[index]),
        } for index, date in enumerate(dates))
    frame = pd.DataFrame(rows)
    bounds = temporal_boundaries(frame["date"])
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / f"{name}.csv.gz"
    manifest_path = output_dir / f"{name}.manifest.json"
    frame.to_csv(data_path, index=False, compression="gzip")
    manifest = DatasetManifest(
        dataset=f"Controlled scenario: {name}", source="Rayventory deterministic generator",
        seed=seed, series_count=series_count, row_count=len(frame),
        date_start=dates.min().date().isoformat(), date_end=dates.max().date().isoformat(),
        history_days=days, horizon_days=28, files={"data": data_path.name}, **bounds,
    )
    manifest_path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return data_path, manifest_path


def benchmark_scenarios(
    output_root: Path,
    experiments_root: Path,
    models: list[str],
    config: TrainingConfig,
    folds: int = 1,
    series_count: int = 12,
    days: int = 360,
    runner: Callable = run_experiment,
) -> dict:
    benchmark_id = datetime.now(timezone.utc).strftime("SCENARIO-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6].upper()
    directory = output_root / benchmark_id
    results = []
    started = time.perf_counter()
    for name in SCENARIOS:
        data_path, manifest_path = generate_scenario(name, directory / "data", series_count, days, config.seed)
        experiment = runner(data_path, manifest_path, experiments_root, models, config, folds=folds)
        ranking = sorted(experiment["results"], key=lambda item: item["metrics"]["wape_pct"])
        neural = [item for item in ranking if item["model"] in models]
        results.append({
            "scenario": name,
            "experiment_id": experiment["experiment_id"],
            "winner": ranking[0]["model"],
            "best_neural": neural[0]["model"] if neural else None,
            "results": ranking,
        })
    neural_summary = {}
    for model in models:
        model_results = [next(item for item in scenario["results"] if item["model"] == model) for scenario in results]
        neural_summary[model] = {
            "mean_wape_pct": round(float(np.mean([item["metrics"]["wape_pct"] for item in model_results])), 4),
            "training_seconds": round(float(sum(item["training_seconds"] for item in model_results)), 3),
            "parameter_count": max(item["parameter_count"] for item in model_results),
            "scenario_wins": sum(scenario["best_neural"] == model for scenario in results),
        }
    document = {
        "benchmark_id": benchmark_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenarios": results,
        "models": neural_summary,
        "config": asdict(config),
        "folds": folds,
        "series_count": series_count,
        "days": days,
        "total_seconds": round(time.perf_counter() - started, 3),
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return document
