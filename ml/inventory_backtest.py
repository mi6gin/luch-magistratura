"""Causal lost-sales inventory simulation; assumptions are not observed warehouse data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .forecasting import _project_dates, _recover_oos_demand
from .purchasing import plan_order
from .runtime_policy import _croston_sba


def simulate(frame: pd.DataFrame, start: str, end: str, *, initial_stock: float,
             lead_time: int = 7, review_days: int = 7, pack_size: int = 1,
             minimum_order_quantity: int = 1, safety_stock_days: int = 0,
             series_limit: int = 20) -> dict:
    if not np.isfinite(initial_stock) or initial_stock < 0:
        raise ValueError("Initial stock must be finite and non-negative.")
    if not 1 <= lead_time <= 365 or review_days < 1 or series_limit < 1:
        raise ValueError("Invalid simulation timing or series limit.")
    data = frame.copy()
    if not {"id", "date", "sales"}.issubset(data):
        raise ValueError("Expected id, date and sales columns.")
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    data["sales"] = pd.to_numeric(data["sales"], errors="raise")
    if data[["id", "date", "sales"]].isna().any().any() or (data["sales"] < 0).any() or not np.isfinite(data["sales"]).all():
        raise ValueError("Sales and identifiers must be valid; returns need separate preparation.")
    if data.duplicated(["id", "date"]).any():
        raise ValueError("Duplicate series/date rows.")
    dates = pd.date_range(start, end)
    if not len(dates):
        raise ValueError("Empty simulation period.")
    methods = ("seasonal_naive_7", "croston_sba", "seasonal-robust-v1")
    details, excluded = [], []
    # Cohort order depends only on pre-test identifiers/history, not test performance.
    eligible = sorted(data.loc[data["date"] < dates[0], "id"].astype(str).unique())[:series_limit]
    data["id"] = data["id"].astype(str)
    for series_id in eligible:
        group = data.loc[data["id"] == series_id].sort_values("date")
        test = group.loc[group["date"].between(dates[0], dates[-1])]
        history = group.loc[group["date"] < dates[0]]
        history_dates = pd.date_range(history["date"].min(), dates[0] - pd.Timedelta(days=1))
        if len(history) < 56 or not pd.DatetimeIndex(history["date"]).equals(history_dates) or not pd.DatetimeIndex(test["date"]).equals(dates):
            excluded.append({"id": series_id, "reason": "incomplete-daily-history"})
            continue
        if "in_stock" in test and pd.to_numeric(test["in_stock"], errors="coerce").eq(0).any():
            excluded.append({"id": series_id, "reason": "observed-test-sales-censored"})
            continue
        for method in methods:
            on_hand = float(initial_stock)
            pending, orders, stocks = {}, [], []
            lost = served = demand_total = 0.0
            shortage_days = 0
            for day, observed in enumerate(test.itertuples(index=False)):
                on_hand += pending.pop(day, 0.0)
                if day % review_days == 0:
                    past = group.loc[group["date"] < observed.date].rename(columns={
                        "date": "sale_date", "sales": "quantity_sold", "sell_price": "sale_price",
                        "is_event": "is_holiday", "snap": "is_promo",
                    }).copy()
                    past["product_id"] = 1
                    for column, default in (("in_stock", 1), ("is_promo", 0), ("is_holiday", 0)):
                        if column not in past:
                            past[column] = default
                    past = _recover_oos_demand(past)
                    horizon = lead_time + review_days + safety_stock_days
                    future = pd.date_range(observed.date, periods=horizon)
                    if method == "seasonal-robust-v1":
                        projection, _, _ = _project_dates(past, future, "standard")
                        point = projection["q50"]
                    else:
                        values = past["recovered_demand"].tail(90).to_numpy(dtype=float)
                        point = values[-7:][np.arange(horizon) % 7] if method == "seasonal_naive_7" else np.repeat(_croston_sba(values), horizon)
                    receipts = [pending.get(day + i, 0.0) for i in range(horizon)]
                    forecast = {"q10": point, "q50": point, "q90": point, "receipts": receipts, "selected_quantile": "q50"}
                    product = {"current_quantity": on_hand, "lead_time": lead_time,
                               "target_cover_days": lead_time + review_days, "safety_stock_days": safety_stock_days,
                               "pack_size": pack_size, "minimum_order_quantity": minimum_order_quantity,
                               "stock_as_of": observed.date}
                    quantity = plan_order(product, forecast, as_of=observed.date)["order_quantity"]
                    if quantity:
                        pending[day + lead_time] = pending.get(day + lead_time, 0) + quantity
                        orders.append(quantity)
                actual = float(observed.sales)
                fulfilled = min(on_hand, actual)
                on_hand -= fulfilled
                served += fulfilled
                demand_total += actual
                lost += actual - fulfilled
                shortage_days += actual > fulfilled + 1e-9
                stocks.append(on_hand)
            details.append({"id": series_id, "method": method, "observed_demand": demand_total,
                            "served_units": served, "lost_units": lost, "stockout_days": shortage_days,
                            "average_stock": float(np.mean(stocks)), "ending_stock": on_hand,
                            "ending_in_transit": float(sum(pending.values())),
                            "orders": len(orders), "ordered_units": sum(orders)})
    if not details:
        raise ValueError("No complete uncensored series available for simulation.")
    summaries = []
    for method in methods:
        rows = [row for row in details if row["method"] == method]
        total = sum(row["observed_demand"] for row in rows)
        summaries.append({"method": method, "series": len(rows),
                          "fill_rate_pct": 100 * sum(row["served_units"] for row in rows) / total if total else None,
                          "lost_units": sum(row["lost_units"] for row in rows),
                          "stockout_days": sum(row["stockout_days"] for row in rows),
                          "average_stock_per_series": float(np.mean([row["average_stock"] for row in rows])),
                          "orders": sum(row["orders"] for row in rows), "ordered_units": sum(row["ordered_units"] for row in rows)})
    return {"purpose": "simulation, not evidence of deployment", "start": start, "end": end,
            "assumptions": {"initial_stock_per_series": initial_stock, "lead_time_days": lead_time,
                            "review_days": review_days, "pack_size": pack_size,
                            "minimum_order_quantity": minimum_order_quantity, "safety_stock_days": safety_stock_days,
                            "receipts": "simulated orders arrive before sales after fixed lead time",
                            "shortages": "lost sales, no backorders", "perishability": "not modeled",
                            "demand_proxy": "historical observed sales; unknown availability is not latent demand"},
            "summary": summaries, "series_results": details, "excluded": excluded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--initial-stock", type=float, required=True)
    parser.add_argument("--lead-time", type=int, default=7)
    parser.add_argument("--review-days", type=int, default=7)
    parser.add_argument("--pack-size", type=int, default=1)
    parser.add_argument("--minimum-order", type=int, default=1)
    parser.add_argument("--safety-days", type=int, default=0)
    parser.add_argument("--series", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = simulate(pd.read_csv(args.data, dtype={"id": str}), args.start, args.end,
                      initial_stock=args.initial_stock, lead_time=args.lead_time, review_days=args.review_days,
                      pack_size=args.pack_size, minimum_order_quantity=args.minimum_order,
                      safety_stock_days=args.safety_days, series_limit=args.series)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=True))


if __name__ == "__main__":
    main()
