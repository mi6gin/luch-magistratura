"""Frozen, resumable IUP study. Each measurement runs in a fresh process."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path


MODELS = ("lstm", "gru", "transformer")
SEEDS = (42, 43, 44)


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def worker(request: Path) -> None:
    from .experiment import run_experiment
    from .scalability import _peak_memory_mb
    from .trainer import TrainingConfig
    job = json.loads(request.read_text(encoding="utf-8"))
    started = time.perf_counter()
    result = run_experiment(Path(job["data"]), Path(job["manifest"]), Path(job["artifacts"]),
                            [job["model"]], TrainingConfig(**job["config"]),
                            folds=1, evaluation_split=job["split"])
    result["resource_measurement"] = {
        "pid": os.getpid(), "fresh_process": True,
        "peak_memory_mb": _peak_memory_mb(),
        "scope": "whole worker process including imports, dataset, training and inference",
        "wall_seconds": time.perf_counter() - started,
        "threads": os.environ.get("OMP_NUM_THREADS"),
    }
    write(Path(job["result"]), result)


def run_job(root: Path, label: str, data: Path, manifest: Path, model: str,
            config: dict, split: str = "test") -> dict:
    destination = root / "results" / f"{label}.json"
    request = {"data": str(data.resolve()), "manifest": str(manifest.resolve()),
               "artifacts": str((root / "artifacts").resolve()), "model": model,
               "config": config, "split": split, "result": str(destination.resolve())}
    request_path = root / "requests" / f"{label}.json"
    if request_path.exists():
        previous = json.loads(request_path.read_text(encoding="utf-8"))
        if previous != request:
            raise ValueError(f"Frozen job changed: {label}; use a new study directory")
    write(request_path, request)
    if not destination.exists():
        print(f"START {label}", flush=True)
        env = {**os.environ, "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "PYTHONUTF8": "1"}
        subprocess.run([sys.executable, "-m", "ml.research.study", "--worker", str(request_path)],
                       check=True, env=env)
    result = json.loads(destination.read_text(encoding="utf-8"))
    print(f"DONE {label}", flush=True)
    return result


def main(source: Path, root: Path, pilot: Path) -> None:
    import pandas as pd
    from .data import prepare_uci_online_retail
    from .scenarios import SCENARIOS, generate_scenario
    from .trainer import TrainingConfig
    from .tuning import trial_grid
    root = root.resolve()
    pilot_ids = sorted(pd.read_csv(pilot, dtype={"id": str})["id"].unique().tolist())
    protocol = {
        "version": 1, "dataset": "UCI Online Retail II, UK positive non-cancelled transactions",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "excluded_pilot_ids": pilot_ids, "selection_cutoff": "2011-09-16",
        "cohort": "training active-day quartiles, stable seeded hash; 300 pool, first 100 stratified IDs",
        "seeds": list(SEEDS), "models": list(MODELS),
        "tuning": {"trials": trial_grid(list(MODELS), "full"), "epochs": 20,
                   "patience": 4, "seed": 42, "selection": "minimum validation WAPE; tie by trial order"},
        "final": "one reserved 28-day test per architecture and prespecified seed; no retuning",
        "scenarios": {"names": list(SCENARIOS), "series": 12, "days": 540,
                      "seeds": list(SEEDS), "epochs": 20, "config": "fixed hidden32/history90/lr0.001"},
        "scale": {"sizes": [10, 100, 300], "seeds": [42, 43], "epochs": 3,
                  "config": "fixed hidden32/history90/lr0.001", "fresh_process_per_job": True},
        "metrics": ["WAPE", "MAE", "RMSE", "Bias", "risk_cost", "coverage", "segments"],
        "resource_scope": "whole fresh worker process, two CPU threads; sequential jobs",
        "limitations": ["sales, not latent demand; availability unknown", "single retailer",
                        "pilot excluded by SKU, shared dates; no fully external retailer test",
                        "synthetic scenarios use historical factors; no future promotion causal claim"],
    }
    protocol_path = root / "protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text(encoding="utf-8")) != protocol:
        raise ValueError("Protocol changed; start a new study directory")
    write(protocol_path, protocol)
    pool = root / "data" / "pool"
    if not (pool / "manifest.json").exists():
        prepare_uci_online_retail(source, pool, 300, selection_cutoff="2011-09-16", exclude_series=set(pilot_ids))
    frame = pd.read_csv(pool / "uci_online_retail_subset.csv.gz", dtype={"id": str})
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    ids = frame["id"].drop_duplicates().tolist()
    if len(ids) != 300:
        raise ValueError("Study requires 300 eligible training-period series")
    subsets = {}
    for size in (10, 100, 300):
        directory = root / "data" / str(size)
        data = directory / "data.csv.gz"
        subset_manifest = directory / "manifest.json"
        subset = frame.loc[frame["id"].isin(ids[:size])]
        directory.mkdir(parents=True, exist_ok=True)
        subset.to_csv(data, index=False, compression="gzip")
        write(subset_manifest, {**manifest, "series_count": size, "row_count": len(subset),
                                "files": {"data": data.name}})
        subsets[size] = (data, subset_manifest)
    base = asdict(TrainingConfig(hidden_size=32, batch_size=256, max_epochs=20, patience=4))
    trials = []
    for index, parameters in enumerate(protocol["tuning"]["trials"], 1):
        config = {**base, **{k: v for k, v in parameters.items() if k != "model"}}
        result = run_job(root, f"tune-{index:02d}", *subsets[100], parameters["model"], config, "validation")
        metric = next(r for r in result["results"] if r["model"] == parameters["model"])["metrics"]["wape_pct"]
        trials.append({"trial": index, "model": parameters["model"], "config": config, "validation_wape": metric})
    selected = {model: min((t for t in trials if t["model"] == model), key=lambda t: (t["validation_wape"], t["trial"]))
                for model in MODELS}
    write(root / "selection.json", {"test_used": False, "trials": trials, "selected": selected})
    final = []
    for model in MODELS:
        for seed in SEEDS:
            final.append(run_job(root, f"final-{model}-{seed}", *subsets[100], model,
                                 {**selected[model]["config"], "seed": seed}))
    scenarios = []
    for scenario in SCENARIOS:
        data, meta = generate_scenario(scenario, root / "data" / scenario, 12, 540, 42)
        for model in MODELS:
            for seed in SEEDS:
                result = run_job(root, f"scenario-{scenario}-{model}-{seed}", data, meta, model, {**base, "seed": seed})
                scenarios.append({"scenario": scenario, "model": model, "seed": seed, "experiment": result})
    scaling = []
    for size in (10, 100, 300):
        for model in MODELS:
            for seed in (42, 43):
                result = run_job(root, f"scale-{size}-{model}-{seed}", *subsets[size], model,
                                 {**base, "max_epochs": 3, "patience": 3, "seed": seed}, "validation")
                scaling.append({"series": size, "model": model, "seed": seed, "experiment": result})
    write(root / "study.json", {"protocol": protocol, "selection": selected, "final": final,
                                "scenarios": scenarios, "scaling": scaling,
                                "environment": {"python": sys.version, "platform": platform.platform()}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pilot", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
    elif all((args.source, args.output, args.pilot)):
        main(args.source, args.output, args.pilot)
    else:
        parser.error("Provide --source, --output and --pilot, or --worker")
