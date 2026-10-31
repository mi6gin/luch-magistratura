from __future__ import annotations

from typing import Any


QUANTILES = (0.1, 0.5, 0.9)
DEFAULT_PARAMETERIZATION = "zero_inflated_lognormal_v3"


def require_torch() -> tuple[Any, Any]:
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise RuntimeError("Установите исследовательские зависимости: pip install -r requirements-ml.txt") from exc
    return torch, nn


def build_model(name: str, feature_count: int, history_days: int = 90, horizon_days: int = 28, hidden_size: int = 64,
                quantile_parameterization: str = DEFAULT_PARAMETERIZATION):
    torch, nn = require_torch()
    if quantile_parameterization not in {"sorted_clamped_v1", "softplus_increments_v2", DEFAULT_PARAMETERIZATION}:
        raise ValueError("Unsupported quantile parameterization")

    def ordered_quantiles(raw):
        values = raw.reshape(-1, horizon_days, len(QUANTILES))
        if quantile_parameterization == "sorted_clamped_v1":
            return torch.sort(values, dim=-1).values.clamp_min(0)
        if quantile_parameterization == DEFAULT_PARAMETERIZATION:
            positive = torch.sigmoid(values[..., :1]).clamp(1e-6, 1 - 1e-6)
            zero = 1 - positive
            levels = torch.tensor(QUANTILES, dtype=values.dtype, device=values.device)
            conditional = ((levels - zero) / positive).clamp(1e-6, 1 - 1e-6)
            mu = values[..., 1:2].clamp(-12, 12)
            sigma = nn.functional.softplus(values[..., 2:3]).clamp(1e-3, 5)
            quantiles = torch.exp(mu + sigma * (2 ** 0.5) * torch.erfinv(2 * conditional - 1))
            return torch.where(levels <= zero, torch.zeros_like(quantiles), quantiles)
        # Positive increments preserve order without zeroing the gradient of
        # initially negative outputs. Old checkpoints retain their old rule.
        return torch.cumsum(nn.functional.softplus(values), dim=-1)

    class RecurrentQuantileModel(nn.Module):
        def __init__(self, cell: str):
            super().__init__()
            recurrent = nn.LSTM if cell == "lstm" else nn.GRU
            self.encoder = recurrent(feature_count, hidden_size, batch_first=True)
            self.dropout = nn.Dropout(0.2)
            self.head = nn.Linear(hidden_size, horizon_days * len(QUANTILES))
            self.quantile_parameterization = quantile_parameterization

        def forward(self, values):
            return ordered_quantiles(self.raw_parameters(values))

        def raw_parameters(self, values):
            encoded, _ = self.encoder(values)
            return self.head(self.dropout(encoded[:, -1]))

    class TransformerQuantileModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.input_projection = nn.Linear(feature_count, hidden_size)
            self.position = nn.Parameter(torch.zeros(1, history_days, hidden_size))
            layer = nn.TransformerEncoderLayer(hidden_size, 4, hidden_size * 2, 0.1, batch_first=True)
            self.encoder = nn.TransformerEncoder(layer, 2)
            self.head = nn.Linear(hidden_size, horizon_days * len(QUANTILES))
            self.quantile_parameterization = quantile_parameterization

        def forward(self, values):
            return ordered_quantiles(self.raw_parameters(values))

        def raw_parameters(self, values):
            encoded = self.encoder(self.input_projection(values) + self.position[:, : values.shape[1]])
            return self.head(encoded.mean(dim=1))

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


def model_loss(model, values, actual):
    """Proper mixture likelihood learns occurrence even when all quantiles are zero."""
    if model.quantile_parameterization != DEFAULT_PARAMETERIZATION:
        return pinball_loss(model(values), actual)
    torch, nn = require_torch()
    raw = model.raw_parameters(values).reshape(*actual.shape, 3)
    positive = actual > 0
    occurrence = nn.functional.binary_cross_entropy_with_logits(raw[..., 0], positive.to(actual.dtype))
    mu = raw[..., 1].clamp(-12, 12)
    sigma = nn.functional.softplus(raw[..., 2]).clamp(1e-3, 5)
    log_y = torch.log(actual.clamp_min(1e-8))
    nll = torch.log(sigma) + log_y + 0.5 * ((log_y - mu) / sigma) ** 2 + 0.5 * 1.8378770664093453
    return occurrence + torch.where(positive, nll, torch.zeros_like(nll)).mean()
