"""Run a saved neural prototype on a frozen, normalized public-data example."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .dataset import FEATURES
from .models import build_model, require_torch


def predict(checkpoint_path: Path, example_path: Path) -> dict:
    torch, _ = require_torch()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    example = json.loads(example_path.read_text(encoding="utf-8"))
    config = checkpoint["config"]
    values = np.asarray(example["normalized_history"], dtype=np.float32)
    if example["features"] != list(FEATURES):
        raise ValueError("Feature order differs from the trained prototype")
    if values.ndim != 2 or values.shape[1] != checkpoint["feature_count"] or not np.isfinite(values).all():
        raise ValueError("Invalid example tensor")
    history = config["history_days"]
    if len(values) < history or example["sales_scale"] <= 0:
        raise ValueError("Insufficient history or invalid normalization scale")
    model = build_model(checkpoint["model"], checkpoint["feature_count"], history,
                        config["horizon_days"], config["hidden_size"],
                        checkpoint.get("quantile_parameterization", "sorted_clamped_v1"))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    with torch.no_grad():
        forecast = model(torch.from_numpy(values[-history:][None])).numpy()[0] * example["sales_scale"]
    return {"model": checkpoint["model"], "series_id": example["series_id"],
            "forecast_start": example["forecast_start"], "source": example["source"],
            "purpose": "public UCI research example; not a warehouse production forecast",
            "q10": forecast[:, 0].tolist(), "q50": forecast[:, 1].tolist(), "q90": forecast[:, 2].tolist()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(predict(args.checkpoint, args.example), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result)
