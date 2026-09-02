from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42


@dataclass(frozen=True)
class DatasetManifest:
    dataset: str
    source: str
    seed: int
    series_count: int
    row_count: int
    date_start: str
    date_end: str
    history_days: int
    horizon_days: int
    train_end: str
    validation_end: str
    test_end: str
    files: dict[str, str]


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)


def temporal_boundaries(dates: pd.Series, validation_days: int = 56, test_days: int = 28) -> dict[str, str]:
    unique = pd.DatetimeIndex(pd.to_datetime(dates).drop_duplicates()).sort_values()
    if len(unique) <= validation_days + test_days + 90:
        raise ValueError("Для эксперимента требуется минимум 175 дней истории.")
    return {
        "train_end": unique[-validation_days - test_days - 1].date().isoformat(),
        "validation_end": unique[-test_days - 1].date().isoformat(),
        "test_end": unique[-1].date().isoformat(),
    }


def _stable_rank(value: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def select_series(metadata: pd.DataFrame, limit: int, seed: int = SEED) -> pd.DataFrame:
    if limit < 1:
        raise ValueError("Количество рядов должно быть положительным.")
    frame = metadata.copy()
    frame["_rank"] = frame["id"].astype(str).map(lambda value: _stable_rank(value, seed))
    group_columns = [column for column in ["dept_id", "store_id"] if column in frame]
    if not group_columns:
        return frame.sort_values("_rank").head(limit).drop(columns="_rank")
    ordered = frame.sort_values(group_columns + ["_rank"])
    groups = list(ordered.groupby(group_columns, sort=True, observed=True))
    selected = []
    while len(selected) < limit:
        changed = False
        for _, group in groups:
            offset = len(selected) // max(len(groups), 1)
            if offset < len(group) and len(selected) < limit:
                selected.append(group.iloc[offset])
                changed = True
        if not changed:
            break
    return pd.DataFrame(selected).drop(columns="_rank").reset_index(drop=True)


def prepare_m5(raw_dir: Path, output_dir: Path, series_limit: int = 300, seed: int = SEED) -> DatasetManifest:
    sales_path = raw_dir / "sales_train_evaluation.csv"
    calendar_path = raw_dir / "calendar.csv"
    prices_path = raw_dir / "sell_prices.csv"
    missing = [path.name for path in (sales_path, calendar_path, prices_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Отсутствуют файлы M5: {', '.join(missing)}")

    sales = pd.read_csv(sales_path)
    id_columns = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
    selected = select_series(sales[id_columns], min(series_limit, len(sales)), seed)
    subset = sales.loc[sales["id"].isin(selected["id"])].copy()
    day_columns = [column for column in subset if column.startswith("d_")]
    long = subset.melt(id_vars=id_columns, value_vars=day_columns, var_name="d", value_name="sales")

    calendar_columns = ["d", "date", "wday", "month", "year", "event_name_1", "event_type_1", "snap_CA", "snap_TX", "snap_WI", "wm_yr_wk"]
    calendar = pd.read_csv(calendar_path, usecols=calendar_columns)
    long = long.merge(calendar, on="d", how="left", validate="many_to_one")
    prices = pd.read_csv(prices_path)
    prices = prices.loc[prices["item_id"].isin(selected["item_id"]) & prices["store_id"].isin(selected["store_id"])]
    long = long.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left", validate="many_to_one")
    long["date"] = pd.to_datetime(long["date"])
    long["is_event"] = long["event_name_1"].notna().astype("int8")
    long["snap"] = np.select(
        [long["state_id"].eq("CA"), long["state_id"].eq("TX"), long["state_id"].eq("WI")],
        [long["snap_CA"], long["snap_TX"], long["snap_WI"]],
        default=0,
    ).astype("int8")
    long["sell_price"] = long.groupby("id", observed=True)["sell_price"].transform(lambda values: values.ffill().bfill()).fillna(0)
    output = long[["date", "id", "item_id", "dept_id", "cat_id", "store_id", "state_id", "sales", "sell_price", "wday", "month", "year", "is_event", "snap"]].sort_values(["id", "date"])
    bounds = temporal_boundaries(output["date"])
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "m5_subset.csv.gz"
    output.to_csv(data_path, index=False, compression="gzip")
    manifest = DatasetManifest(
        dataset="M5 Forecasting Accuracy",
        source="https://www.kaggle.com/competitions/m5-forecasting-accuracy",
        seed=seed,
        series_count=int(output["id"].nunique()),
        row_count=len(output),
        date_start=output["date"].min().date().isoformat(),
        date_end=output["date"].max().date().isoformat(),
        history_days=int(output["date"].nunique()),
        horizon_days=28,
        train_end=bounds["train_end"],
        validation_end=bounds["validation_end"],
        test_end=bounds["test_end"],
        files={"data": data_path.name},
    )
    (output_dir / "manifest.json").write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def prepare_uci_online_retail(source: Path, output_dir: Path, series_limit: int = 300, seed: int = SEED) -> DatasetManifest:
    if not source.is_file():
        raise FileNotFoundError(f"Файл UCI Online Retail II не найден: {source}")
    sheets = pd.read_excel(source, sheet_name=None)
    transactions = pd.concat(sheets.values(), ignore_index=True)
    transactions.columns = [str(column).strip() for column in transactions.columns]
    required = {"Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Country"}
    if not required.issubset(transactions.columns):
        raise ValueError(f"В UCI-файле отсутствуют колонки: {', '.join(sorted(required - set(transactions.columns)))}")
    transactions["Invoice"] = transactions["Invoice"].astype(str)
    transactions["StockCode"] = transactions["StockCode"].astype(str).str.strip()
    transactions["InvoiceDate"] = pd.to_datetime(transactions["InvoiceDate"], errors="coerce")
    transactions["Quantity"] = pd.to_numeric(transactions["Quantity"], errors="coerce")
    transactions["Price"] = pd.to_numeric(transactions["Price"], errors="coerce")
    valid = transactions.loc[
        ~transactions["Invoice"].str.upper().str.startswith("C")
        & transactions["InvoiceDate"].notna()
        & transactions["Quantity"].gt(0)
        & transactions["Price"].gt(0)
        & transactions["StockCode"].str.match(r"^[0-9]{4,6}[A-Z]?$", na=False)
        & transactions["Country"].eq("United Kingdom")
    ].copy()
    if valid.empty:
        raise ValueError("После очистки UCI Online Retail II не осталось продаж.")
    valid["date"] = valid["InvoiceDate"].dt.normalize()
    valid["revenue"] = valid["Quantity"] * valid["Price"]
    daily = valid.groupby(["StockCode", "date"], observed=True).agg(
        sales=("Quantity", "sum"), revenue=("revenue", "sum"), description=("Description", "first")
    ).reset_index()
    daily["sell_price"] = daily["revenue"] / daily["sales"]
    profile = daily.groupby("StockCode", observed=True).agg(
        active_days=("date", "nunique"), total_sales=("sales", "sum"), description=("description", "first")
    ).reset_index()
    eligible = profile.loc[profile["active_days"] >= 60].copy()
    if eligible.empty:
        raise ValueError("Недостаточно товаров минимум с 60 активными днями продаж.")
    eligible["dept_id"] = pd.qcut(eligible["active_days"].rank(method="first"), 4, labels=["sporadic", "slow", "regular", "frequent"])
    eligible["store_id"] = "UK-online"
    eligible = eligible.rename(columns={"StockCode": "id"})
    selected = select_series(eligible[["id", "dept_id", "store_id"]], min(series_limit, len(eligible)), seed)
    chosen = daily.loc[daily["StockCode"].isin(selected["id"])].rename(columns={"StockCode": "id"})
    dates = pd.date_range(chosen["date"].min(), chosen["date"].max(), freq="D")
    grid = pd.MultiIndex.from_product([selected["id"], dates], names=["id", "date"]).to_frame(index=False)
    output = grid.merge(chosen[["id", "date", "sales", "sell_price", "description"]], on=["id", "date"], how="left")
    output["sales"] = output["sales"].fillna(0).astype(float)
    output["sell_price"] = output.groupby("id", observed=True)["sell_price"].transform(lambda values: values.ffill()).fillna(0)
    output["description"] = output.groupby("id", observed=True)["description"].transform(lambda values: values.ffill().bfill())
    output["wday"] = output["date"].dt.dayofweek + 1
    output["month"] = output["date"].dt.month
    output["year"] = output["date"].dt.year
    output["is_event"] = 0
    output["snap"] = 0
    bounds = temporal_boundaries(output["date"])
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "uci_online_retail_subset.csv.gz"
    output.to_csv(data_path, index=False, compression="gzip")
    manifest = DatasetManifest(
        dataset="UCI Online Retail II",
        source="https://doi.org/10.24432/C5CG6D",
        seed=seed,
        series_count=int(output["id"].nunique()),
        row_count=len(output),
        date_start=output["date"].min().date().isoformat(),
        date_end=output["date"].max().date().isoformat(),
        history_days=int(output["date"].nunique()),
        horizon_days=28,
        train_end=bounds["train_end"],
        validation_end=bounds["validation_end"],
        test_end=bounds["test_end"],
        files={"data": data_path.name},
    )
    (output_dir / "manifest.json").write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
