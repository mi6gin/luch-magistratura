"""Reproducible external M5 food-sales and production purchasing-policy validation.

Run from repository root: python -m ml.research.external_validation --archive PATH --output PATH
The protocol is frozen separately; results never select cohorts, checkpoints or policies.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
import time
import zipfile

import numpy as np
import pandas as pd

from ..forecasting import _project_dates, _recover_oos_demand
from ..purchasing import plan_order
from ..runtime_policy import _croston_sba
from .dataset import FEATURES, make_windows, normalize_from_train
from .metrics import point_metrics
from .models import build_model, require_torch
from .trainer import TrainingConfig, train_model

PROTOCOL = Path(__file__).resolve().parents[2] / "docs/research/external-validation/protocol.json"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(archive: Path, protocol: dict) -> pd.DataFrame:
    with zipfile.ZipFile(archive) as source:
        calendar = pd.read_csv(source.open("calendar.csv"))
        calendar["date"] = pd.to_datetime(calendar["date"])
        if not pd.DatetimeIndex(calendar.date).equals(pd.date_range("2011-01-29", periods=len(calendar))):
            raise ValueError("Unexpected M5 calendar ordering")
        calendar["d"] = [f"d_{i + 1}" for i in range(len(calendar))]
        # Item selection reads ONLY training columns, never validation/test totals.
        train_days = calendar.loc[calendar.date.between(protocol["data_start"], protocol["train_end"]), "d"].tolist()
        sales = pd.read_csv(source.open("sales_train_evaluation.csv"), usecols=["item_id", "dept_id", "store_id", *train_days])
        sales["id"] = sales.item_id + "_" + sales.store_id
        sales = sales.loc[sales.store_id.eq("CA_1") & sales.dept_id.str.startswith("FOODS_")]
        early = train_days[:90]
        recent = calendar.loc[calendar.date.between("2015-01-01", protocol["train_end"]), "d"].tolist()
        eligible = sales.loc[(sales[early].sum(axis=1) > 0) & ((sales[recent] > 0).sum(axis=1) >= 60)].copy()
        eligible["selection_hash"] = eligible.id.map(lambda value: hashlib.sha256(value.encode()).hexdigest())
        chosen = eligible.sort_values("selection_hash").groupby("dept_id", sort=True).head(protocol["series_per_department"])
        if len(chosen) != 3 * protocol["series_per_department"]:
            raise ValueError("Insufficient eligible series for frozen cohort")
        ids = sorted(chosen.id)
        day_columns = calendar.loc[calendar.date.between(protocol["data_start"], protocol["test_end"]), "d"].tolist()
        full = pd.read_csv(source.open("sales_train_evaluation.csv"), usecols=["item_id", "dept_id", "store_id", *day_columns])
        full["id"] = full.item_id + "_" + full.store_id
        full = full.loc[full.id.isin(ids)]
        selected_prices = []
        for chunk in pd.read_csv(source.open("sell_prices.csv"), chunksize=250000):
            selected_prices.append(chunk.loc[chunk.store_id.eq("CA_1") & chunk.item_id.isin(full.item_id)])
        prices = pd.concat(selected_prices, ignore_index=True)
    long = full.melt(id_vars=["id", "item_id", "dept_id", "store_id"], var_name="d", value_name="sales")
    long = long.merge(calendar[["d", "date", "wday", "month", "wm_yr_wk", "event_name_1", "snap_CA"]], on="d", validate="many_to_one")
    long = long.merge(prices, on=["item_id", "store_id", "wm_yr_wk"], how="left", validate="many_to_one")
    long = long.sort_values(["id", "date"]).reset_index(drop=True)
    long["sell_price"] = long.groupby("id").sell_price.ffill().fillna(0)
    long["is_event"] = long.event_name_1.notna().astype(int)
    long["snap"] = long.snap_CA.astype(int)
    return long[["id", "date", "sales", "sell_price", "wday", "month", "is_event", "snap", "dept_id"]]


def window_at(group: pd.DataFrame, date: pd.Timestamp, history: int) -> np.ndarray:
    # A hard causal boundary applies even when the caller has loaded future rows.
    past = group.loc[group.date < date].tail(history)
    if len(past) != history or past.date.iloc[-1] != date - pd.Timedelta(days=1):
        raise ValueError("Incomplete causal window")
    return past[list(FEATURES)].to_numpy(dtype=np.float32)


def baseline_predictions(group, date, horizon):
    past = group.loc[group.date < date].copy()
    values = past.sales.tail(90).to_numpy(float)
    result = {
        "seasonal_naive_7": values[-7:][np.arange(horizon) % 7],
        "median_28": np.repeat(np.median(values[-28:]), horizon),
        "croston_sba": np.repeat(_croston_sba(values), horizon),
    }
    runtime = past.rename(columns={"date": "sale_date", "sales": "quantity_sold", "sell_price": "sale_price", "is_event": "is_holiday", "snap": "is_promo"})
    runtime["product_id"], runtime["in_stock"] = 1, 1
    runtime = _recover_oos_demand(runtime)
    result["seasonal-robust-v1"] = _project_dates(runtime, pd.date_range(date, periods=horizon), "standard")[0]["q50"]
    return result


def simulate_series(actual, forecasts, initial_stock, lead, review, safety, start):
    """Receipts -> review -> demand; production policy, explicit mass conservation."""
    actual = np.asarray(actual, dtype=float)
    forecasts = np.asarray(forecasts, dtype=float)
    horizon = lead + review + safety
    if forecasts.shape[0] != len(actual) or forecasts.shape[1] < horizon:
        raise ValueError("Forecast dimensions do not cover the simulation")
    if not np.isfinite(actual).all() or (actual < 0).any() or not np.isfinite(forecasts).all() or (forecasts < 0).any():
        raise ValueError("Invalid demand/forecast")
    stock = float(initial_stock)
    pending, stocks, daily = {}, [], []
    served = lost = received = ordered = 0.0
    orders = shortages = 0
    for day, demand in enumerate(actual):
        receipt = pending.pop(day, 0.0)
        received += receipt
        stock += receipt
        quantity = 0
        if day % review == 0:
            date = pd.Timestamp(start) + pd.Timedelta(days=day)
            point = forecasts[day, :horizon]
            forecast = {"q10": point, "q50": point, "q90": point, "selected_quantile": "q50",
                        "receipts": [pending.get(day + offset, 0.0) for offset in range(horizon)]}
            product = {"current_quantity": stock, "lead_time": lead, "target_cover_days": lead + review,
                       "safety_stock_days": safety, "pack_size": 1, "minimum_order_quantity": 1, "stock_as_of": date}
            quantity = plan_order(product, forecast, as_of=date)["order_quantity"]
            if quantity:
                pending[day + lead] = pending.get(day + lead, 0) + quantity
                ordered += quantity
                orders += 1
        fulfilled = min(stock, demand)
        stock -= fulfilled
        served += fulfilled
        lost += demand - fulfilled
        shortages += demand > fulfilled + 1e-9
        stocks.append(stock)
        daily.append((receipt, quantity, fulfilled, demand - fulfilled, stock))
    if abs(initial_stock + received - served - stock) > 1e-7 or abs(ordered - received - sum(pending.values())) > 1e-7:
        raise AssertionError("Inventory mass balance violated")
    return {"demand": float(actual.sum()), "served": served, "lost": lost, "average_stock": float(np.mean(stocks)),
            "stockout_days": shortages, "initial_stock": initial_stock, "received": received, "ordered": ordered,
            "orders": orders, "ending_stock": stock, "ending_in_transit": float(sum(pending.values()))}, daily


def bootstrap_differences(actual, predictions, primary, ids):
    """Paired SKU resampling preserves all dates and both forecast blocks together."""
    rng = np.random.default_rng(20261101)
    indices = rng.integers(0, len(ids), size=(10000, len(ids)))
    demand = actual.sum(axis=1)
    base = "seasonal_naive_7"
    errors = {method: np.abs(value - actual).sum(axis=1) for method, value in predictions.items()}
    inventory = {method: group.set_index("id").loc[ids] for method, group in primary.groupby("method")}
    out = []
    for method in predictions:
        if method == base:
            continue
        wape = 100 * (errors[method] - errors[base])[indices].sum(axis=1) / demand[indices].sum(axis=1)
        fill = 100 * (inventory[method].served.to_numpy() - inventory[base].served.to_numpy())[indices].sum(axis=1) / demand[indices].sum(axis=1)
        stock = (inventory[method].average_stock.to_numpy() - inventory[base].average_stock.to_numpy())[indices].mean(axis=1)
        out.append({"method": method, "wape_difference_pp": float(100 * (errors[method] - errors[base]).sum() / demand.sum()),
                    "wape_ci95": np.quantile(wape, [.025, .975]).tolist(),
                    "fill_difference_pp": float(100 * (inventory[method].served.sum() - inventory[base].served.sum()) / demand.sum()),
                    "fill_ci95": np.quantile(fill, [.025, .975]).tolist(),
                    "stock_difference": float((inventory[method].average_stock - inventory[base].average_stock).mean()),
                    "stock_ci95": np.quantile(stock, [.025, .975]).tolist()})
    return out


def run(archive: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    (output / "protocol.json").write_bytes(PROTOCOL.read_bytes())
    torch, _ = require_torch()
    torch.set_num_threads(2)
    frame = prepare(archive, protocol)
    frame.to_csv(output / "cohort.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    ids = sorted(frame.id.unique())
    normalized, scales = normalize_from_train(frame, protocol["train_end"])
    train = make_windows(normalized, None, protocol["train_end"], 90, 28, stride=protocol["train_stride"])
    validation = make_windows(normalized, "2016-01-01", protocol["validation_end"], 90, 28, stride=protocol["validation_stride"])
    groups = [normalized.loc[normalized.id.eq(series)] for series in ids]
    raw_groups = [frame.loc[frame.id.eq(series)] for series in ids]
    dates = pd.date_range(protocol["test_start"], protocol["test_end"])
    inputs = np.stack([window_at(group, date, 90) for group in groups for date in dates])
    factors = np.repeat([scales.sales[series] for series in ids], len(dates))[:, None, None]
    cached, training, seed_metrics = {}, [], []
    actual = np.stack([group.loc[group.date.isin(dates), "sales"].to_numpy(float) for group in raw_groups])
    for name in protocol["models"]:
        runs = []
        for seed in protocol["seeds"]:
            config = TrainingConfig(hidden_size=protocol["hidden_size"], batch_size=protocol["batch_size"],
                                    max_epochs=protocol["max_epochs"], patience=protocol["patience"], seed=seed)
            folder = output / "weights" / str(seed)
            folder.mkdir(parents=True, exist_ok=True)
            log_path = folder / f"{name}.json"
            if log_path.exists():
                record = json.loads(log_path.read_text(encoding="utf-8"))
                if record["protocol_sha256"] != sha(PROTOCOL) or record["cohort_sha256"] != sha(output / "cohort.csv.gz"):
                    raise ValueError("Refusing to reuse checkpoint from different protocol/data")
                record = record["training"]
            else:
                print(f"TRAIN {name} seed={seed} windows={len(train[0])}", flush=True)
                record = train_model(name, train, validation, folder, config)
                log_path.write_text(json.dumps({"protocol_sha256": sha(PROTOCOL), "cohort_sha256": sha(output / "cohort.csv.gz"),
                                                "training": record}, indent=2), encoding="utf-8")
            print(f"DONE {name} seed={seed} epochs={record['epochs']} seconds={record['training_seconds']}", flush=True)
            training.append({"seed": seed, **record})
            model = build_model(name, len(FEATURES), 90, 28, config.hidden_size, config.quantile_parameterization)
            checkpoint = torch.load(folder / f"{name}.pt", map_location="cpu", weights_only=True)
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            with torch.no_grad():
                prediction = np.concatenate([model(torch.from_numpy(inputs[i:i+128])).numpy() for i in range(0, len(inputs), 128)])
            prediction = (prediction * factors).reshape(len(ids), len(dates), 28, 3)
            if not np.isfinite(prediction).all() or (np.diff(prediction, axis=-1) < -1e-7).any():
                raise AssertionError("Invalid neural quantiles")
            runs.append(prediction)
            point = np.concatenate([prediction[:, 0, :, 1], prediction[:, 28, :, 1]], axis=1)
            seed_metrics.append({"method": name, "seed": seed, **point_metrics(actual, point)})
        cached[name] = np.mean(runs, axis=0)
    for method in protocol["baselines"]:
        cached[method] = np.empty((len(ids), len(dates), 28, 3), dtype=float)
    for index, group in enumerate(raw_groups):
        for day, date in enumerate(dates):
            for method, point in baseline_predictions(group, date, 28).items():
                cached[method][index, day] = np.repeat(np.asarray(point)[:, None], 3, axis=1)
    np.savez_compressed(output / "daily-forecasts.npz", ids=np.asarray(ids), dates=np.asarray(dates.astype(str)), **cached)
    predictions, forecast_rows, forecast_summary = {}, [], []
    for method, values in cached.items():
        selected = np.concatenate([values[:, 0], values[:, 28]], axis=1)
        predictions[method] = selected[..., 1]
        record = {"method": method, **point_metrics(actual, selected[..., 1])}
        if method in protocol["models"]:
            record["coverage_80_pct"] = float(((actual >= selected[..., 0]) & (actual <= selected[..., 2])).mean() * 100)
        forecast_summary.append(record)
        for index, series in enumerate(ids):
            for day, date in enumerate(dates):
                forecast_rows.append({"id": series, "date": date.date().isoformat(), "origin": dates[(day // 28) * 28].date().isoformat(),
                                      "method": method, "actual": actual[index, day], "q10": selected[index, day, 0],
                                      "q50": selected[index, day, 1], "q90": selected[index, day, 2]})
    pd.DataFrame(forecast_rows).to_csv(output / "forecast-test.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    inventory_rows, daily_rows = [], []
    inventory_protocol = protocol["inventory"]
    for lead, review, safety in itertools.product(inventory_protocol["lead_days"], inventory_protocol["review_days"], inventory_protocol["safety_days"]):
        primary = {"lead_days": lead, "review_days": review, "safety_days": safety} == inventory_protocol["primary"]
        scenario = f"L{lead}_R{review}_S{safety}"
        for method, values in cached.items():
            for index, series in enumerate(ids):
                initial = int(np.ceil(raw_groups[index].loc[raw_groups[index].date < dates[0], "sales"].tail(28).mean() * (lead + review)))
                result, daily = simulate_series(actual[index], values[index, :, :, 1], initial, lead, review, safety, dates[0])
                inventory_rows.append({"scenario": scenario, "primary": primary, "id": series, "method": method, **result})
                if primary:
                    for day, row in enumerate(daily):
                        daily_rows.append(dict(zip(["receipts", "order", "served", "lost", "ending_stock"], row),
                                               id=series, date=dates[day].date().isoformat(), method=method, demand=actual[index, day]))
    inventory = pd.DataFrame(inventory_rows)
    inventory.to_csv(output / "inventory-series.csv", index=False)
    pd.DataFrame(daily_rows).to_csv(output / "inventory-primary-daily.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    inventory_summary = []
    for (scenario, method), rows in inventory.groupby(["scenario", "method"]):
        inventory_summary.append({"scenario": scenario, "method": method, "primary": bool(rows.primary.iloc[0]),
                                  "fill_rate_pct": float(100 * rows.served.sum() / rows.demand.sum()),
                                  "average_stock_per_series": float(rows.average_stock.mean()), "lost_units": float(rows.lost.sum()),
                                  "orders": int(rows.orders.sum()), "ordered_units": float(rows.ordered.sum())})
    pd.DataFrame(inventory_summary).to_csv(output / "inventory-summary.csv", index=False)
    result = {"protocol": protocol, "series": len(ids), "departments": frame.groupby("dept_id").id.nunique().to_dict(),
              "test_days": len(dates), "test_sales": float(actual.sum()), "training_windows": len(train[0]), "validation_windows": len(validation[0]),
              "forecast_metrics": forecast_summary, "seed_metrics": seed_metrics, "training": training, "inventory": inventory_summary,
              "paired_cluster_bootstrap": bootstrap_differences(actual, predictions, inventory.loc[inventory.primary], ids),
              "environment": {"python": sys.version, "platform": platform.platform(), "torch": torch.__version__, "numpy": np.__version__, "pandas": pd.__version__, "torch_threads": 2},
              "sha256": {"source_archive": sha(archive), "protocol": sha(PROTOCOL), "cohort": sha(output / "cohort.csv.gz"),
                         **{str(path.relative_to(Path(__file__).resolve().parents[2])): sha(path) for path in [Path(__file__), Path(__file__).parents[1] / "purchasing.py", Path(__file__).parent / "models.py", Path(__file__).parent / "trainer.py"]}}}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"forecast": forecast_summary, "primary_inventory": [r for r in inventory_summary if r["primary"]]}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.archive, args.output)


if __name__ == "__main__":
    main()
