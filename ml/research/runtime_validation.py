"""Validate the exact deployed hybrid, with routes fixed before the test period."""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from ..forecasting import _project_dates, _recover_oos_demand
    from ..runtime_policy import POLICY_CONTRACT, POLICY_RUNTIME, apply_policy
except ImportError:
    from forecasting import _project_dates, _recover_oos_demand
    from runtime_policy import POLICY_CONTRACT, POLICY_RUNTIME, apply_policy
from .metrics import point_metrics, interval_coverage


def validate_runtime(frame: pd.DataFrame, routes: dict, start: str, end: str) -> dict:
    actuals, candidates, baselines, lowers, uppers = [], [], [], [], []
    fallback_series = 0
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    for _, group in frame.groupby("id", sort=True):
        group = group.sort_values("date")
        history = group.loc[group["date"] < pd.Timestamp(start)].copy()
        test = group.loc[group["date"].between(pd.Timestamp(start), pd.Timestamp(end))]
        expected = pd.date_range(start, end)
        if len(history) < 28 or not pd.DatetimeIndex(test["date"]).equals(expected):
            continue
        if "in_stock" in test and pd.to_numeric(test["in_stock"], errors="coerce").eq(0).any():
            continue
        history = history.rename(columns={"date": "sale_date", "sales": "quantity_sold", "sell_price": "sale_price", "snap": "is_promo", "is_event": "is_holiday"})
        history["product_id"] = 1
        if "in_stock" not in history:
            history["in_stock"] = 1
        history = _recover_oos_demand(history)
        dates = pd.DatetimeIndex(test["date"])
        projection, profile, _ = _project_dates(history, dates, "standard")
        calibrated, _, warning = apply_policy({"routes": routes}, history, projection,
                                              dates=dates, reference_level=profile.get("policy_reference_level"),
                                              sanity_cap=profile.get("sanity_cap"))
        fallback_series += warning is not None
        actuals.extend(test["sales"].to_numpy(dtype=float))
        candidates.extend(calibrated["q50"])
        baselines.extend(projection["q50"])
        lowers.extend(calibrated["q10"])
        uppers.extend(calibrated["q90"])
    if not actuals:
        raise ValueError("Для проверки рабочего алгоритма нет полных тестовых рядов без дефицита.")
    return {"runtime": POLICY_RUNTIME, "contract": POLICY_CONTRACT, "routes": dict(routes),
            "evaluation_split": "test", "start": start, "end": end, "observations": len(actuals),
            "actual_volume": float(sum(actuals)), "fallback_series": fallback_series,
            "metrics": {**point_metrics(np.asarray(actuals), np.asarray(candidates)),
                        "coverage_pct": interval_coverage(actuals, lowers, uppers)},
            "baseline_metrics": point_metrics(np.asarray(actuals), np.asarray(baselines)),
            "baseline_model": "seasonal-robust-v1", "future_covariates": "history-only"}
