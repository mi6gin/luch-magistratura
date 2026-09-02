from __future__ import annotations

import copy
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .metrics import interval_coverage, point_metrics, quantiles_are_ordered, segment_metrics
from .models import build_model, pinball_loss, require_torch


@dataclass(frozen=True)
class TrainingConfig:
    history_days: int = 90
    horizon_days: int = 28
    hidden_size: int = 64
    batch_size: int = 64
    max_epochs: int = 100
    patience: int = 10
    learning_rate: float = 0.001
    seed: int = 42


def _loader(values, batch_size: int, shuffle: bool):
    torch, _ = require_torch()
    x, y, _ = values
    dataset = torch.utils.data.TensorDataset(torch.from_numpy(x), torch.from_numpy(y))
    generator = torch.Generator().manual_seed(42)
    return torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, generator=generator)


def _loss(model, loader, device) -> float:
    torch, _ = require_torch()
    model.eval()
    total, batches = 0.0, 0
    with torch.no_grad():
        for x, y in loader:
            total += float(pinball_loss(model(x.to(device)), y.to(device)).item())
            batches += 1
    return total / max(batches, 1)


def train_model(name: str, train, validation, output_dir: Path, config: TrainingConfig) -> dict:
    torch, _ = require_torch()
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = build_model(name, train[0].shape[-1], config.history_days, config.horizon_days, config.hidden_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    train_loader = _loader(train, config.batch_size, True)
    validation_loader = _loader(validation, config.batch_size, False)
    best_loss, best_state, stale_epochs = float("inf"), None, 0
    started = time.perf_counter()
    epochs = 0
    history = []
    for epoch in range(config.max_epochs):
        model.train()
        train_total, train_batches = 0.0, 0
        for x, y in train_loader:
            optimizer.zero_grad()
            loss = pinball_loss(model(x.to(device)), y.to(device))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_total += float(loss.item())
            train_batches += 1
        validation_loss = _loss(model, validation_loader, device)
        history.append({
            "epoch": epoch + 1,
            "train_loss": round(train_total / max(train_batches, 1), 6),
            "validation_loss": round(validation_loss, 6),
        })
        epochs = epoch + 1
        if validation_loss < best_loss - 1e-5:
            best_loss = validation_loss
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
                break
    model.load_state_dict(best_state or model.state_dict())
    output_dir.mkdir(parents=True, exist_ok=True)
    weights = output_dir / f"{name}.pt"
    torch.save({"state_dict": model.state_dict(), "config": asdict(config), "feature_count": train[0].shape[-1]}, weights)
    return {
        "model": name,
        "epochs": epochs,
        "best_validation_loss": round(best_loss, 6),
        "training_seconds": round(time.perf_counter() - started, 3),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "device": str(device),
        "weights": weights.name,
        "loss_history": history,
    }


def evaluate_model(name: str, checkpoint_path: Path, test, sales_scales: dict[str, float]) -> dict:
    torch, _ = require_torch()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    config = TrainingConfig(**checkpoint["config"])
    model = build_model(name, checkpoint["feature_count"], config.history_days, config.horizon_days, config.hidden_size)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    started = time.perf_counter()
    with torch.no_grad():
        prediction = model(torch.from_numpy(test[0])).numpy()
    inference_ms = (time.perf_counter() - started) * 1000
    scales = np.asarray([sales_scales[series_id] for series_id in test[2]], dtype=float)[:, None]
    actual = test[1] * scales
    lower, median, upper = (prediction[..., index] * scales for index in range(3))
    return {
        **point_metrics(actual, median),
        "coverage_pct": interval_coverage(actual, lower, upper),
        "quantiles_ordered": quantiles_are_ordered(prediction),
        "inference_ms": round(inference_ms, 3),
        "test_windows": len(actual),
        "segments": segment_metrics(actual, median, test[0][..., 0]),
    }


def save_result(path: Path, result: dict) -> None:
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
