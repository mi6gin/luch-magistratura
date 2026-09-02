from __future__ import annotations

import json
import resource
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .data import DatasetManifest, temporal_boundaries
from .experiment import run_experiment
from .trainer import TrainingConfig


def _peak_memory_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def benchmark_scalability(
    data_path: Path,
    manifest_path: Path,
    output_root: Path,
    experiments_root: Path,
    models: list[str],
    sizes: list[int],
    config: TrainingConfig,
) -> dict:
    frame = pd.read_csv(data_path, parse_dates=["date"], dtype={"id": str}, low_memory=False)
    frame["id"] = frame["id"].astype(str)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    available = sorted(frame["id"].unique())
    requested = sorted(set(size for size in sizes if size > 0))
    if not requested:
        raise ValueError("Укажите хотя бы один положительный размер выборки.")
    benchmark_id = datetime.now(timezone.utc).strftime("SCALE-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6].upper()
    directory = output_root / benchmark_id
    data_directory = directory / "data"
    data_directory.mkdir(parents=True, exist_ok=True)
    results = []
    for requested_size in requested:
        size = min(requested_size, len(available))
        subset = frame.loc[frame["id"].isin(available[:size])].copy()
        bounds = temporal_boundaries(subset["date"])
        subset_path = data_directory / f"series-{size}.csv.gz"
        subset_manifest_path = data_directory / f"series-{size}.manifest.json"
        subset.to_csv(subset_path, index=False, compression="gzip")
        subset_manifest = DatasetManifest(
            dataset=f"{manifest['dataset']} scalability {size} series",
            source=manifest["source"], seed=int(manifest.get("seed", config.seed)),
            series_count=size, row_count=len(subset),
            date_start=subset["date"].min().date().isoformat(),
            date_end=subset["date"].max().date().isoformat(),
            history_days=int(subset["date"].nunique()), horizon_days=config.horizon_days,
            files={"data": subset_path.name}, **bounds,
        )
        subset_manifest_path.write_text(json.dumps(asdict(subset_manifest), ensure_ascii=False, indent=2), encoding="utf-8")
        started = time.perf_counter()
        experiment = run_experiment(subset_path, subset_manifest_path, experiments_root, models, config, folds=1)
        raw_results = {item["model"]: item for item in experiment["folds"][-1]["results"]}
        peak_memory_mb = _peak_memory_mb()
        results.append({
            "requested_series": requested_size,
            "series": size,
            "rows": len(subset),
            "wall_seconds": round(time.perf_counter() - started, 3),
            "process_peak_memory_mb": round(peak_memory_mb, 2),
            "experiment_id": experiment["experiment_id"],
            "models": [{
                "model": item["model"],
                "wape_pct": item["metrics"]["wape_pct"],
                "training_seconds": item["training_seconds"],
                "inference_ms": raw_results[item["model"]]["metrics"].get("inference_ms", 0),
                "parameter_count": item["parameter_count"],
            } for item in experiment["results"] if item["model"] in models],
        })
        if size == len(available):
            break
    document = {
        "benchmark_id": benchmark_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": manifest["dataset"],
        "config": asdict(config),
        "results": results,
    }
    (directory / "result.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return document
