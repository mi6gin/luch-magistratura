from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FEATURES = ("sales_scaled", "price_scaled", "wday_sin", "wday_cos", "month_sin", "month_cos", "is_event", "snap")


@dataclass(frozen=True)
class SeriesScales:
    sales: dict[str, float]
    price: dict[str, float]


def normalize_from_train(frame: pd.DataFrame, train_end: str) -> tuple[pd.DataFrame, SeriesScales]:
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    train = data.loc[data["date"] <= pd.Timestamp(train_end)]
    if train.empty:
        raise ValueError("Train-период не содержит наблюдений.")
    sales_scales = train.groupby("id", observed=True)["sales"].quantile(0.9).clip(lower=1).to_dict()
    price_scales = train.groupby("id", observed=True)["sell_price"].median().clip(lower=0.01).to_dict()
    data["sales_scaled"] = data["sales"] / data["id"].map(sales_scales).fillna(1)
    data["price_scaled"] = data["sell_price"] / data["id"].map(price_scales).fillna(1)
    data["wday_sin"] = np.sin(2 * np.pi * (data["wday"] - 1) / 7)
    data["wday_cos"] = np.cos(2 * np.pi * (data["wday"] - 1) / 7)
    data["month_sin"] = np.sin(2 * np.pi * (data["month"] - 1) / 12)
    data["month_cos"] = np.cos(2 * np.pi * (data["month"] - 1) / 12)
    return data, SeriesScales(sales=sales_scales, price=price_scales)


def make_windows(
    frame: pd.DataFrame,
    start: str | None,
    end: str,
    history_days: int = 90,
    horizon_days: int = 28,
    stride: int = 7,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    inputs, targets, series_ids = [], [], []
    start_date = pd.Timestamp(start) if start else None
    end_date = pd.Timestamp(end)
    for series_id, group in frame.groupby("id", sort=True, observed=True):
        group = group.sort_values("date").reset_index(drop=True)
        feature_values = group[list(FEATURES)].to_numpy(dtype=np.float32)
        target_values = group["sales_scaled"].to_numpy(dtype=np.float32)
        dates = pd.to_datetime(group["date"])
        for position in range(history_days, len(group) - horizon_days + 1, stride):
            forecast_start = dates.iloc[position]
            forecast_end = dates.iloc[position + horizon_days - 1]
            if (start_date is not None and forecast_start < start_date) or forecast_end > end_date:
                continue
            inputs.append(feature_values[position - history_days : position])
            targets.append(target_values[position : position + horizon_days])
            series_ids.append(str(series_id))
    if not inputs:
        raise ValueError("Для указанного периода не сформировано ни одного окна.")
    return np.stack(inputs), np.stack(targets), series_ids


def load_experiment_data(path: str, manifest: dict, history_days: int = 90, horizon_days: int = 28):
    frame = pd.read_csv(path, parse_dates=["date"])
    normalized, scales = normalize_from_train(frame, manifest["train_end"])
    train = make_windows(normalized, None, manifest["train_end"], history_days, horizon_days)
    validation_start = (pd.Timestamp(manifest["train_end"]) + pd.Timedelta(days=1)).date().isoformat()
    validation = make_windows(normalized, validation_start, manifest["validation_end"], history_days, horizon_days, stride=1)
    test_start = (pd.Timestamp(manifest["validation_end"]) + pd.Timedelta(days=1)).date().isoformat()
    test = make_windows(normalized, test_start, manifest["test_end"], history_days, horizon_days, stride=1)
    return frame, scales, train, validation, test

