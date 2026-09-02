from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import demand_type


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or abs(denominator) < 1e-9:
        return None
    return round(float(numerator / denominator), 4)


def analyze_dataset(data_path: Path, manifest_path: Path, output_path: Path | None = None) -> dict:
    started = time.perf_counter()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame = pd.read_csv(data_path, parse_dates=["date"])
    required = {"id", "date", "sales", "sell_price", "is_event", "snap"}
    if missing := sorted(required - set(frame.columns)):
        raise ValueError(f"Для анализа отсутствуют колонки: {', '.join(missing)}")
    frame["sales"] = pd.to_numeric(frame["sales"], errors="coerce")
    frame["sell_price"] = pd.to_numeric(frame["sell_price"], errors="coerce")
    invalid_sales = int(frame["sales"].isna().sum())
    negative_sales = int(frame["sales"].lt(0).sum())
    duplicate_rows = int(frame.duplicated(["id", "date"]).sum())
    clean = frame.dropna(subset=["id", "date", "sales"]).copy()
    clean["sales"] = clean["sales"].clip(lower=0)

    profiles = []
    for series_id, group in clean.groupby("id", sort=True, observed=True):
        values = group.sort_values("date")["sales"].to_numpy(dtype=float)
        positive = values[values > 0]
        profiles.append({
            "id": str(series_id),
            "history_days": int(len(values)),
            "active_days": int(len(positive)),
            "zero_sales_pct": round(float(np.mean(values == 0) * 100), 2),
            "mean_demand": round(float(values.mean()), 4),
            "demand_type": demand_type(values),
        })
    profile = pd.DataFrame(profiles)
    types = profile["demand_type"].value_counts().reindex(["smooth", "intermittent", "erratic", "lumpy"], fill_value=0)

    ordered = clean.sort_values(["id", "date"])
    lagged = ordered.groupby("id", observed=True)["sales"].shift(7)
    valid_lag = lagged.notna()
    current_lag_values = ordered.loc[valid_lag, "sales"]
    previous_lag_values = lagged.loc[valid_lag]
    weekly_correlation = (
        current_lag_values.corr(previous_lag_values)
        if valid_lag.any() and current_lag_values.std() > 0 and previous_lag_values.std() > 0
        else np.nan
    )
    daily_total = clean.groupby("date", observed=True)["sales"].sum().sort_index()
    if len(daily_total) > 1 and daily_total.mean() > 0:
        slope = float(np.polyfit(np.arange(len(daily_total)), daily_total.to_numpy(dtype=float), 1)[0])
        trend_30d_pct = round(slope * 30 / float(daily_total.mean()) * 100, 2)
    else:
        trend_30d_pct = 0.0

    event_mean = clean.loc[clean["is_event"].astype(bool), "sales"].mean()
    regular_mean = clean.loc[~clean["is_event"].astype(bool), "sales"].mean()
    promo_mean = clean.loc[clean["snap"].astype(bool), "sales"].mean()
    nonpromo_mean = clean.loc[~clean["snap"].astype(bool), "sales"].mean()
    price_rows = clean.loc[clean["sell_price"].gt(0) & clean["sales"].notna(), ["sell_price", "sales"]]
    price_correlation = (
        price_rows["sell_price"].corr(price_rows["sales"])
        if len(price_rows) > 2 and price_rows["sell_price"].std() > 0 and price_rows["sales"].std() > 0
        else np.nan
    )

    result = {
        "dataset": manifest.get("dataset", "Неизвестный набор"),
        "source": manifest.get("source"),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "period": {
            "start": clean["date"].min().date().isoformat(),
            "end": clean["date"].max().date().isoformat(),
            "days": int(clean["date"].nunique()),
        },
        "volume": {"series": int(clean["id"].nunique()), "rows": int(len(clean))},
        "quality": {
            "duplicate_series_dates": duplicate_rows,
            "missing_sales": invalid_sales,
            "negative_sales": negative_sales,
            "minimum_history_days": int(profile["history_days"].min()),
            "median_history_days": round(float(profile["history_days"].median()), 1),
        },
        "demand": {
            "zero_sales_pct": round(float(clean["sales"].eq(0).mean() * 100), 2),
            "mean": round(float(clean["sales"].mean()), 4),
            "median": round(float(clean["sales"].median()), 4),
            "p90": round(float(clean["sales"].quantile(0.9)), 4),
            "p99": round(float(clean["sales"].quantile(0.99)), 4),
            "types": {key: int(value) for key, value in types.items()},
        },
        "patterns": {
            "weekly_lag_correlation": None if not np.isfinite(weekly_correlation) else round(float(weekly_correlation), 4),
            "portfolio_trend_30d_pct": trend_30d_pct,
            "event_uplift": _safe_ratio(event_mean, regular_mean),
            "promo_uplift": _safe_ratio(promo_mean, nonpromo_mean),
            "price_demand_correlation": None if not np.isfinite(price_correlation) else round(float(price_correlation), 4),
        },
        "performance": {
            "input_mb": round(data_path.stat().st_size / 1024 / 1024, 3),
            "analysis_seconds": round(time.perf_counter() - started, 4),
        },
        "series_preview": sorted(profiles, key=lambda item: (-item["zero_sales_pct"], item["id"]))[:10],
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
