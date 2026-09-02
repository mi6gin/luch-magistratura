from __future__ import annotations

from typing import Any


QUANTILES = (0.1, 0.5, 0.9)


def require_torch() -> tuple[Any, Any]:
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise RuntimeError("Установите исследовательские зависимости: pip install -r requirements-ml.txt") from exc
    return torch, nn


def build_model(name: str, feature_count: int, history_days: int = 90, horizon_days: int = 28, hidden_size: int = 64):
    torch, nn = require_torch()

    class RecurrentQuantileModel(nn.Module):
        def __init__(self, cell: str):
            super().__init__()
            recurrent = nn.LSTM if cell == "lstm" else nn.GRU
            self.encoder = recurrent(feature_count, hidden_size, batch_first=True)
            self.dropout = nn.Dropout(0.2)
            self.head = nn.Linear(hidden_size, horizon_days * len(QUANTILES))

        def forward(self, values):
            encoded, _ = self.encoder(values)
            raw = self.head(self.dropout(encoded[:, -1]))
            return torch.sort(raw.reshape(-1, horizon_days, len(QUANTILES)), dim=-1).values.clamp_min(0)

    class TransformerQuantileModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.input_projection = nn.Linear(feature_count, hidden_size)
            self.position = nn.Parameter(torch.zeros(1, history_days, hidden_size))
            layer = nn.TransformerEncoderLayer(hidden_size, 4, hidden_size * 2, 0.1, batch_first=True)
            self.encoder = nn.TransformerEncoder(layer, 2)
            self.head = nn.Linear(hidden_size, horizon_days * len(QUANTILES))

        def forward(self, values):
            encoded = self.encoder(self.input_projection(values) + self.position[:, : values.shape[1]])
            raw = self.head(encoded.mean(dim=1))
            return torch.sort(raw.reshape(-1, horizon_days, len(QUANTILES)), dim=-1).values.clamp_min(0)

    normalized = name.lower().strip()
    if normalized in {"lstm", "gru"}:
        return RecurrentQuantileModel(normalized)
    if normalized == "transformer":
        return TransformerQuantileModel()
    raise ValueError("Модель должна быть одной из: lstm, gru, transformer")


def pinball_loss(predictions, actual):
    torch, _ = require_torch()
    target = actual.unsqueeze(-1)
    quantiles = torch.tensor(QUANTILES, device=predictions.device, dtype=predictions.dtype)
    error = target - predictions
    return torch.maximum(quantiles * error, (quantiles - 1) * error).mean()
