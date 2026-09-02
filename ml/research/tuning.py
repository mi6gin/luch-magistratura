from __future__ import annotations

import itertools
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .experiment import run_experiment
from .trainer import TrainingConfig


def trial_grid(models: list[str], preset: str) -> list[dict]:
    if preset not in {"smoke", "full"}:
        raise ValueError("Tuning preset должен быть smoke или full.")
    values = {
        "hidden_size": [32] if preset == "smoke" else [32, 64],
        "learning_rate": [0.001] if preset == "smoke" else [0.001, 0.0003],
        "history_days": [90] if preset == "smoke" else [60, 90],
    }
    return [
        {"model": model, "hidden_size": hidden, "learning_rate": learning_rate, "history_days": history}
        for model, hidden, learning_rate, history in itertools.product(
            models, values["hidden_size"], values["learning_rate"], values["history_days"]
        )
    ]


def tune_models(
    data_path: Path,
    manifest_path: Path,
    experiments_root: Path,
    output_root: Path,
    models: list[str],
    preset: str = "smoke",
    folds: int = 1,
    epochs: int = 3,
    patience: int = 2,
    batch_size: int = 256,
    runner: Callable = run_experiment,
) -> dict:
    tuning_id = datetime.now(timezone.utc).strftime("TUNE-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6].upper()
    trials = []
    for index, parameters in enumerate(trial_grid(models, preset), start=1):
        config = TrainingConfig(
            history_days=parameters["history_days"],
            hidden_size=parameters["hidden_size"],
            learning_rate=parameters["learning_rate"],
            max_epochs=epochs,
            patience=patience,
            batch_size=batch_size,
        )
        print(f"trial {index}: {parameters}", flush=True)
        experiment = runner(data_path, manifest_path, experiments_root, [parameters["model"]], config, folds=folds)
        result = next(item for item in experiment["results"] if item["model"] == parameters["model"])
        trials.append({
            "trial": index,
            "experiment_id": experiment["experiment_id"],
            "model": parameters["model"],
            "parameters": asdict(config),
            "metrics": result["metrics"],
            "training_seconds": result["training_seconds"],
            "parameter_count": result["parameter_count"],
        })
    ranking = sorted(trials, key=lambda item: (item["metrics"]["wape_pct"], item["training_seconds"], item["parameter_count"]))
    best_by_model = {
        model: next(item for item in ranking if item["model"] == model)
        for model in models
    }
    document = {
        "tuning_id": tuning_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preset": preset,
        "folds": folds,
        "epochs": epochs,
        "selection_rule": "minimum WAPE; ties resolved by training time and parameter count",
        "trials": trials,
        "best_by_model": best_by_model,
        "winner": ranking[0],
        "ranking": [item["trial"] for item in ranking],
    }
    directory = output_root / tuning_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return document
