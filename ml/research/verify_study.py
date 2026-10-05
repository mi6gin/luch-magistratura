"""Audit published IUP evidence without retraining or downloading transactions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .demo import predict
from .metrics import point_metrics
from .study import MODELS, SEEDS


def verify(directory: Path) -> dict:
    directory = directory.resolve()
    index = json.loads((directory / "SHA256SUMS.json").read_text(encoding="utf-8"))
    for relative, digest in index.items():
        path = (directory / relative).resolve()
        if directory not in path.parents or not path.is_file():
            raise ValueError(f"Invalid artifact path: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Artifact changed: {relative}")
    document = json.loads((directory / "study.json").read_text(encoding="utf-8"))
    if [len(document[k]) for k in ("tuning", "final", "scenarios", "scaling")] != [24, 9, 36, 18]:
        raise ValueError("Incomplete frozen study")
    scale_keys = [(r["series"], r["model"], r["seed"]) for r in document["scaling"]]
    if sorted(scale_keys) != sorted((size, model, seed) for size in (10, 100, 300) for model in MODELS for seed in (42, 43)):
        raise ValueError("Missing or duplicated scalability measurement")
    if not all(r["experiment"]["resource_measurement"]["fresh_process"] for r in document["scaling"]):
        raise ValueError("Scalability used shared-process memory")
    scenario_keys = [(r["scenario"], r["model"], r["seed"]) for r in document["scenarios"]]
    expected_scenarios = [(scenario, model, seed) for scenario in document["protocol"]["scenarios"]["names"] for model in MODELS for seed in SEEDS]
    if sorted(scenario_keys) != sorted(expected_scenarios):
        raise ValueError("Missing or duplicated scenario repetition")
    for trial in document["tuning"]:
        if trial["evaluation_split"] != "validation" or trial["reserved_test_period"]["evaluated"]:
            raise ValueError("Tuning used reserved test")
    keys = [(d["results"][-1]["model"], d["config"]["seed"]) for d in document["final"]]
    if sorted(keys) != sorted((model, seed) for model in MODELS for seed in SEEDS):
        raise ValueError("Missing or duplicated final repetition")
    for model in MODELS:
        candidates = [(trial["results"][-1]["metrics"]["wape_pct"], index, trial)
                      for index, trial in enumerate(document["tuning"])
                      if trial["results"][-1]["model"] == model]
        chosen = min(candidates, key=lambda t: (t[0], t[1]))[2]
        if chosen["config"] != document["selection"][model]["config"]:
            raise ValueError("Selected configuration differs from the validation rule")
    reference = None
    for final in document["final"]:
        model = final["results"][-1]["model"]
        seed = final["config"]["seed"]
        if final["evaluation_split"] != "test" or final["rolling_folds"] != 1:
            raise ValueError("Invalid final evaluation period")
        expected = {**document["selection"][model]["config"], "seed": seed}
        if final["config"] != expected:
            raise ValueError("Final configuration changed after selection")
        frame = pd.read_csv(directory / "forecasts" / f"{model}-{seed}.csv.gz", dtype={"series_id": str})
        if len(frame) != 2800 or frame["series_id"].nunique() != 100 or frame.duplicated(["series_id", "date"]).any():
            raise ValueError("Incomplete exported forecasts")
        if not frame.groupby("series_id").size().eq(28).all() or set(frame["date"]) != set(pd.date_range("2011-11-12", "2011-12-09").strftime("%Y-%m-%d")):
            raise ValueError("Exported forecasts use a different test period")
        if frame["series_id"].isin(document["protocol"]["excluded_pilot_ids"]).any():
            raise ValueError("Pilot SKU entered final cohort")
        values = frame[["actual", "q10", "q50", "q90"]].to_numpy()
        if not np.isfinite(values).all() or (values < 0).any() or not np.all(values[:, 1] <= values[:, 2]) or not np.all(values[:, 2] <= values[:, 3]):
            raise ValueError("Invalid forecast values")
        metric = point_metrics(frame["actual"].to_numpy(), frame["q50"].to_numpy())["wape_pct"]
        if abs(metric - final["results"][-1]["metrics"]["wape_pct"]) > 0.001:
            raise ValueError("Exported WAPE differs from the frozen result")
        actual = frame[["series_id", "date", "actual"]]
        if reference is not None and not actual.equals(reference):
            raise ValueError("Models were evaluated on different actuals")
        reference = actual
        if not final["resource_measurement"]["fresh_process"]:
            raise ValueError("Final resource measurement used a shared process")
    for size in (100, 300):
        frame = pd.read_csv(directory / "data" / f"{size}.csv.gz", dtype={"id": str})
        if frame["id"].nunique() != size or len(frame) != size * 739:
            raise ValueError("Invalid public research dataset")
        if "CustomerID" in frame or "Customer ID" in frame:
            raise ValueError("Customer data should not be published")
    for model in MODELS:
        forecast = predict(directory / "demo" / f"{model}.pt", directory / "demo/example.json")
        expected = json.loads((directory / "demo" / f"{model}-forecast.json").read_text(encoding="utf-8"))
        for key in ("q10", "q50", "q90"):
            np.testing.assert_allclose(forecast[key], expected[key], atol=0.002, rtol=1e-5)
    return {"passed": True, "hashed_artifacts": len(index), "tuning": 24, "final": 9,
            "scenarios": 36, "scaling": 18, "forecast_rows": 25200, "runnable_prototypes": 3}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.report), ensure_ascii=False))
