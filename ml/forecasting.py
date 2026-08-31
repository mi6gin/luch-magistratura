"""Robust seasonal demand forecasting and inventory decision baseline."""

from __future__ import annotations

import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


MODEL_NAME = "seasonal-robust-v1"
FORECAST_HORIZON = 30
STALE_AFTER_DAYS = 7

STRATEGIES: dict[str, dict[str, Any]] = {
    "standard": {
        "title": "Операционный пульс",
        "description": "Сбалансированный план пополнения по медианному сценарию спроса.",
        "quantile": "q50",
        "trend_strength": 0.15,
        "promo_mode": "calendar",
    },
    "risk": {
        "title": "Антидефицит",
        "description": "Защита доступности товара по верхней границе прогнозного спроса.",
        "quantile": "q90",
        "trend_strength": 0.25,
        "promo_mode": "calendar",
    },
    "optimization": {
        "title": "Свободный капитал",
        "description": "Проверка излишков по нижней границе спроса для высвобождения оборотных средств.",
        "quantile": "q10",
        "trend_strength": 0.0,
        "promo_mode": "calendar",
    },
    "trend": {
        "title": "Радар спроса",
        "description": "Продолжение устойчивого краткосрочного тренда на прогнозный горизонт.",
        "quantile": "q50",
        "trend_strength": 1.0,
        "promo_mode": "calendar",
    },
    "promo": {
        "title": "Промо-разгон",
        "description": "План первой недели кампании с измеренным историческим промо-эффектом.",
        "quantile": "q50",
        "trend_strength": 0.15,
        "promo_mode": "campaign",
    },
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _dedupe_warnings(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    configured = db_path or os.getenv("ML_DB_PATH")
    path = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parent.parent
        / "storage"
        / "app"
        / "rayventory"
        / "inventory_forecast.db"
    )
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    return path


def _recover_oos_demand(sales: pd.DataFrame) -> pd.DataFrame:
    """Recover censored demand without ever borrowing values from another SKU."""
    if sales.empty:
        result = sales.copy()
        result["recovered_demand"] = pd.Series(dtype=float)
        result["was_oos_recovered"] = pd.Series(dtype=bool)
        return result

    recovered_groups: list[pd.DataFrame] = []
    for _, source in sales.groupby("product_id", sort=False, observed=True):
        group = source.sort_values("sale_date", kind="stable").copy()
        demand = pd.to_numeric(group["quantity_sold"], errors="coerce").fillna(0.0).clip(lower=0.0)
        in_stock = pd.to_numeric(group["in_stock"], errors="coerce").fillna(1.0).gt(0)
        observed = demand.where(in_stock)

        dated_observed = pd.Series(observed.to_numpy(), index=group["sale_date"])
        same_week = dated_observed.reindex(group["sale_date"] - pd.Timedelta(days=7)).to_numpy()
        same_week = pd.Series(same_week, index=group.index, dtype=float)
        rolling = observed.shift(1).rolling(28, min_periods=3).median()
        dow_median = observed.groupby(group["sale_date"].dt.dayofweek).transform("median")
        sku_median = _as_float(observed.median(), 0.0)

        replacement = same_week.combine_first(rolling).combine_first(dow_median).fillna(sku_median)
        group["recovered_demand"] = demand.where(in_stock, replacement).clip(lower=0.0)
        group["was_oos_recovered"] = ~in_stock
        recovered_groups.append(group)

    return pd.concat(recovered_groups, ignore_index=True).sort_values(
        ["product_id", "sale_date"], kind="stable"
    ).reset_index(drop=True)


def load_inventory_data(
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load and validate products, sales, stock, and transit from SQLite."""
    path = _resolve_db_path(db_path)
    warnings: list[str] = []

    with sqlite3.connect(str(path), timeout=30) as connection:
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        required = {"products", "sales_history", "warehouse_stock"}
        missing = sorted(required - table_names)
        if missing:
            raise ValueError(f"Database is missing required tables: {', '.join(missing)}")

        products = pd.read_sql_query("SELECT * FROM products", connection)
        sales = pd.read_sql_query("SELECT * FROM sales_history", connection)
        stock = pd.read_sql_query("SELECT * FROM warehouse_stock", connection)
        if "warehouse_in_transit" in table_names:
            transit = pd.read_sql_query("SELECT * FROM warehouse_in_transit", connection)
        else:
            transit = pd.DataFrame(columns=["product_id", "in_transit_quantity"])
            warnings.append("Таблица товаров в пути отсутствует; объём в пути принят равным нулю.")

    product_required = {"id", "name", "category", "lead_time", "unit_price"}
    sales_required = {"product_id", "sale_date", "quantity_sold"}
    if missing_columns := sorted(product_required - set(products.columns)):
        raise ValueError(f"Products table is missing columns: {', '.join(missing_columns)}")
    if missing_columns := sorted(sales_required - set(sales.columns)):
        raise ValueError(f"Sales table is missing columns: {', '.join(missing_columns)}")
    if not {"product_id", "current_quantity"}.issubset(stock.columns):
        raise ValueError("Warehouse stock table must contain product_id and current_quantity.")

    products = products.copy()
    products["id"] = pd.to_numeric(products["id"], errors="raise").astype(int)
    if products["id"].duplicated().any():
        raise ValueError("Products table contains duplicate SKU ids.")
    products["lead_time"] = pd.to_numeric(products["lead_time"], errors="coerce").fillna(1).clip(lower=1).astype(int)
    products["unit_price"] = pd.to_numeric(products["unit_price"], errors="coerce").fillna(0.0).clip(lower=0.0)

    sales = sales.copy()
    sales["product_id"] = pd.to_numeric(sales["product_id"], errors="coerce")
    sales["sale_date"] = pd.to_datetime(sales["sale_date"], errors="coerce").dt.normalize()
    invalid_sales = sales["product_id"].isna() | sales["sale_date"].isna()
    if invalid_sales.any():
        warnings.append(f"Исключено строк с некорректным товаром или датой: {int(invalid_sales.sum())}.")
        sales = sales.loc[~invalid_sales].copy()
    sales["product_id"] = sales["product_id"].astype(int)

    known_products = set(products["id"])
    unknown_products = ~sales["product_id"].isin(known_products)
    if unknown_products.any():
        warnings.append(f"Исключено строк для неизвестных товаров: {int(unknown_products.sum())}.")
        sales = sales.loc[~unknown_products].copy()

    sales["quantity_sold"] = pd.to_numeric(sales["quantity_sold"], errors="coerce").fillna(0.0).clip(lower=0.0)
    for column, default in (("in_stock", 1), ("is_promo", 0), ("is_holiday", 0)):
        if column not in sales.columns:
            sales[column] = default
            warnings.append(f"В продажах нет поля {column}; использовано значение {default}.")
        sales[column] = pd.to_numeric(sales[column], errors="coerce").fillna(default).clip(0, 1).astype(int)

    price_columns = [column for column in ("sale_price", "price", "unit_price") if column in sales.columns]
    aggregate: dict[str, str] = {
        "quantity_sold": "sum",
        "in_stock": "min",
        "is_promo": "max",
        "is_holiday": "max",
    }
    aggregate.update({column: "median" for column in price_columns})
    duplicate_count = int(sales.duplicated(["product_id", "sale_date"]).sum())
    if duplicate_count:
        warnings.append(f"Объединено дублирующихся строк товар/дата: {duplicate_count}.")
    sales = sales.groupby(["product_id", "sale_date"], as_index=False, observed=True).agg(aggregate)
    sales = _recover_oos_demand(sales)

    stock = stock.copy()
    stock["product_id"] = pd.to_numeric(stock["product_id"], errors="coerce")
    stock["current_quantity"] = pd.to_numeric(stock["current_quantity"], errors="coerce").fillna(0.0).clip(lower=0.0)
    stock = stock.dropna(subset=["product_id"])
    stock["product_id"] = stock["product_id"].astype(int)
    stock = stock.groupby("product_id", as_index=False, observed=True)["current_quantity"].last()

    if transit.empty or not {"product_id", "in_transit_quantity"}.issubset(transit.columns):
        transit = pd.DataFrame({"product_id": products["id"], "in_transit_quantity": 0.0})
    else:
        transit = transit.copy()
        transit["product_id"] = pd.to_numeric(transit["product_id"], errors="coerce")
        transit["in_transit_quantity"] = pd.to_numeric(
            transit["in_transit_quantity"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
        transit = transit.dropna(subset=["product_id"])
        transit["product_id"] = transit["product_id"].astype(int)
        transit = transit.groupby("product_id", as_index=False, observed=True)["in_transit_quantity"].sum()

    inventory = products.merge(stock, how="left", left_on="id", right_on="product_id").drop(columns="product_id")
    inventory = inventory.merge(transit, how="left", left_on="id", right_on="product_id").drop(columns="product_id")
    inventory[["current_quantity", "in_transit_quantity"]] = inventory[
        ["current_quantity", "in_transit_quantity"]
    ].fillna(0.0).clip(lower=0.0)

    if sales.empty:
        raise ValueError("Sales history is empty after validation.")
    data_as_of = sales["sale_date"].max().date().isoformat()
    return {
        "db_path": str(path),
        "products": inventory.sort_values("id", kind="stable").reset_index(drop=True),
        "sales": sales,
        "stock": stock,
        "transit": transit,
        "data_as_of": data_as_of,
        "warnings": _dedupe_warnings(warnings),
    }


def _weighted_mean(values: np.ndarray, ages: np.ndarray, half_life: float = 42.0) -> float:
    finite = np.isfinite(values) & np.isfinite(ages)
    if not finite.any():
        return 0.0
    values = values[finite]
    ages = ages[finite]
    if values.size >= 8:
        lower, upper = np.quantile(values, [0.05, 0.95])
        values = np.clip(values, lower, upper)
    weights = np.exp2(-np.maximum(ages, 0.0) / half_life)
    return _as_float(np.average(values, weights=weights), _as_float(np.median(values), 0.0))


def _event_uplifts(history: pd.DataFrame) -> tuple[float, float, int, int]:
    demand = history["recovered_demand"].to_numpy(dtype=float)
    dow = history["sale_date"].dt.dayofweek
    promo = history["is_promo"].astype(bool)
    holiday = history["is_holiday"].astype(bool)
    normal = ~(promo | holiday)

    normal_frame = history.loc[normal, ["sale_date", "recovered_demand"]].copy()
    if normal_frame.empty:
        dow_reference = history.groupby(dow, observed=True)["recovered_demand"].median()
    else:
        dow_reference = normal_frame.groupby(normal_frame["sale_date"].dt.dayofweek, observed=True)[
            "recovered_demand"
        ].median()
    fallback = max(_as_float(np.median(demand), 0.0), 0.1)
    expected = dow.map(dow_reference).fillna(fallback).to_numpy(dtype=float)
    ratio = np.divide(demand, np.maximum(expected, 0.1))

    normal_ratio = _as_float(np.median(ratio[normal.to_numpy()]), 1.0) if normal.any() else 1.0
    promo_only = promo & ~holiday
    holiday_rows = holiday
    promo_samples = int(promo_only.sum())
    holiday_samples = int(holiday_rows.sum())
    promo_ratio = _as_float(np.median(ratio[promo_only.to_numpy()]), normal_ratio) / max(normal_ratio, 0.1)
    holiday_ratio = _as_float(np.median(ratio[holiday_rows.to_numpy()]), normal_ratio) / max(normal_ratio, 0.1)

    promo_uplift = float(np.clip(promo_ratio if promo_samples >= 3 else 1.0, 1.0, 2.25))
    holiday_uplift = float(np.clip(holiday_ratio if holiday_samples >= 3 else 1.0, 1.0, 3.0))
    return promo_uplift, holiday_uplift, promo_samples, holiday_samples


def _build_profile(history: pd.DataFrame) -> dict[str, Any]:
    history = history.sort_values("sale_date", kind="stable").copy()
    promo_uplift, holiday_uplift, promo_samples, holiday_samples = _event_uplifts(history)
    event_factor = np.where(history["is_promo"].to_numpy(dtype=bool), promo_uplift, 1.0)
    event_factor *= np.where(history["is_holiday"].to_numpy(dtype=bool), holiday_uplift, 1.0)
    event_factor = np.clip(event_factor, 1.0, 3.5)
    adjusted = history["recovered_demand"].to_numpy(dtype=float) / event_factor

    last_date = history["sale_date"].max()
    ages = (last_date - history["sale_date"]).dt.days.to_numpy(dtype=float)
    recent = ages <= 180
    if recent.sum() < 28:
        recent = np.ones(len(history), dtype=bool)
    recent_values = adjusted[recent]
    recent_ages = ages[recent]
    recent_dow = history.loc[recent, "sale_date"].dt.dayofweek.to_numpy()
    global_level = _weighted_mean(recent_values, recent_ages)

    dow_levels: dict[int, float] = {}
    for day in range(7):
        mask = recent_dow == day
        dow_levels[day] = _weighted_mean(recent_values[mask], recent_ages[mask]) if mask.any() else global_level
        dow_levels[day] = 0.8 * dow_levels[day] + 0.2 * global_level

    recent_window = adjusted[(ages >= 0) & (ages < 28)]
    prior_window = adjusted[(ages >= 28) & (ages < 56)]
    recent_level = _as_float(np.median(recent_window), global_level) if recent_window.size else global_level
    prior_level = _as_float(np.median(prior_window), global_level) if prior_window.size else global_level
    trend_ratio = float(np.clip(recent_level / max(prior_level, 0.1), 0.75, 1.35))

    fitted = np.array([dow_levels[int(day)] for day in history["sale_date"].dt.dayofweek], dtype=float) * event_factor
    residual = history["recovered_demand"].to_numpy(dtype=float) - fitted
    residual = residual[ages <= 180] if (ages <= 180).sum() >= 28 else residual
    residual_median = _as_float(np.median(residual), 0.0)
    mad = _as_float(np.median(np.abs(residual - residual_median)), 0.0)
    robust_sigma = max(1.4826 * mad, math.sqrt(max(global_level, 1.0)))
    residual_q10, residual_q90 = np.quantile(residual, [0.1, 0.9]) if residual.size else (0.0, 0.0)
    lower_error = min(_as_float(residual_q10), -1.2816 * robust_sigma)
    upper_error = max(_as_float(residual_q90), 1.2816 * robust_sigma)

    historical = history["recovered_demand"].to_numpy(dtype=float)
    hist_median = _as_float(np.median(historical), 0.0)
    hist_mad = _as_float(np.median(np.abs(historical - hist_median)), 0.0)
    hist_q995 = _as_float(np.quantile(historical, 0.995), _as_float(np.max(historical), 0.0))
    sanity_cap = max(hist_q995 * 1.35, hist_median + 8.0 * 1.4826 * hist_mad, global_level * 2.0, 1.0)

    return {
        "dow_levels": dow_levels,
        "global_level": global_level,
        "trend_ratio": trend_ratio,
        "promo_uplift": promo_uplift,
        "holiday_uplift": holiday_uplift,
        "promo_samples": promo_samples,
        "holiday_samples": holiday_samples,
        "lower_error": lower_error,
        "upper_error": upper_error,
        "sanity_cap": float(sanity_cap),
    }


def _recurring_holiday_flags(history: pd.DataFrame, dates: pd.DatetimeIndex) -> np.ndarray:
    holiday_dates = history.loc[history["is_holiday"].astype(bool), "sale_date"]
    if holiday_dates.empty:
        return np.zeros(len(dates), dtype=bool)
    month_days = set(zip(holiday_dates.dt.month, holiday_dates.dt.day))
    return np.array([(date.month, date.day) in month_days for date in dates], dtype=bool)


def _recurring_promo_flags(history: pd.DataFrame, dates: pd.DatetimeIndex) -> np.ndarray:
    daily = history.set_index("sale_date")["is_promo"].astype(bool).sort_index()
    if not daily.any():
        return np.zeros(len(dates), dtype=bool)
    previous = daily.shift(1, fill_value=False)
    previous_dates = daily.index.to_series().diff().eq(pd.Timedelta(days=1)).to_numpy()
    starts = daily.index[daily.to_numpy() & ~(previous.to_numpy() & previous_dates)]
    if len(starts) < 2:
        return np.zeros(len(dates), dtype=bool)

    intervals = np.diff(starts.values).astype("timedelta64[D]").astype(int)
    period = int(np.clip(round(float(np.median(intervals))), 7, 90))
    run_lengths: list[int] = []
    for start in starts:
        run = 0
        cursor = start
        while bool(daily.get(cursor, False)) and run < 14:
            run += 1
            cursor += pd.Timedelta(days=1)
        run_lengths.append(run)
    run_length = int(np.clip(round(float(np.median(run_lengths))), 1, 14))

    result = np.zeros(len(dates), dtype=bool)
    last_start = starts[-1]
    offset = math.floor((dates.min() - last_start).days / period)
    projected_start = last_start + pd.Timedelta(days=offset * period)
    while projected_start <= dates.max():
        result |= (dates >= projected_start) & (dates < projected_start + pd.Timedelta(days=run_length))
        projected_start += pd.Timedelta(days=period)
    return result


def _parse_date_overrides(value: Any, dates: pd.DatetimeIndex, field: str) -> np.ndarray | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be an array of ISO dates.")
    parsed = pd.to_datetime(list(value), errors="coerce")
    if pd.isna(parsed).any():
        raise ValueError(f"{field} contains an invalid date.")
    normalized = {pd.Timestamp(item).normalize() for item in parsed}
    return np.array([date.normalize() in normalized for date in dates], dtype=bool)


def _event_flags(
    history: pd.DataFrame,
    dates: pd.DatetimeIndex,
    strategy: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    warnings: list[str] = []
    promo = _recurring_promo_flags(history, dates)
    holiday = _recurring_holiday_flags(history, dates)

    promo_dates = _parse_date_overrides(overrides.get("promo_dates"), dates, "promo_dates")
    holiday_dates = _parse_date_overrides(overrides.get("holiday_dates"), dates, "holiday_dates")
    if promo_dates is not None:
        promo = promo_dates
    elif "is_promo" in overrides:
        promo = np.full(len(dates), bool(int(overrides["is_promo"])), dtype=bool)
    elif strategy["promo_mode"] == "campaign":
        promo[: min(7, len(promo))] = True
        warnings.append("Первые 7 дней прогноза отмечены как плановая промо-кампания.")

    if holiday_dates is not None:
        holiday = holiday_dates
    elif "is_holiday" in overrides:
        holiday = np.full(len(dates), bool(int(overrides["is_holiday"])), dtype=bool)
    return promo, holiday, warnings


def _price_multiplier(
    history: pd.DataFrame,
    profile: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> tuple[float, list[str]]:
    if "price_change" not in overrides or abs(_as_float(overrides.get("price_change"))) < 1e-12:
        return 1.0, []
    change = _as_float(overrides.get("price_change"), float("nan"))
    if not math.isfinite(change) or change <= -0.95 or change > 3.0:
        raise ValueError("price_change must be a finite fraction in (-0.95, 3.0].")

    price_column = next((column for column in ("sale_price", "price", "unit_price") if column in history.columns), None)
    if price_column is None:
        return 1.0, ["Изменение цены проигнорировано: отсутствует история транзакционных цен."]

    prices = pd.to_numeric(history[price_column], errors="coerce")
    valid = prices.gt(0) & history["recovered_demand"].gt(0)
    if valid.sum() < 30 or prices.loc[valid].nunique() < 3 or prices.loc[valid].std() / prices.loc[valid].mean() < 0.02:
        return 1.0, ["Изменение цены проигнорировано: в истории недостаточно вариативности цен."]

    x = np.log(prices.loc[valid].to_numpy(dtype=float))
    y = np.log(history.loc[valid, "recovered_demand"].to_numpy(dtype=float))
    elasticity = float(np.clip(np.polyfit(x, y, 1)[0], -3.0, 0.5))
    multiplier = float(np.clip((1.0 + change) ** elasticity, 0.5, 1.75))
    return multiplier, [f"Price scenario uses robustly clipped historical elasticity ({elasticity:.2f})."]


def _project_dates(
    history: pd.DataFrame,
    dates: pd.DatetimeIndex,
    strategy_name: str,
    overrides: Mapping[str, Any] | None = None,
    known_promo: np.ndarray | None = None,
    known_holiday: np.ndarray | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any], list[str]]:
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    if history.empty:
        zeros = np.zeros(len(dates), dtype=float)
        warnings = ["Для товара нет пригодной истории продаж."]
        if overrides and abs(_as_float(overrides.get("price_change"))) > 1e-12:
            warnings.append("Изменение цены проигнорировано: отсутствует история транзакционных цен.")
        return {"q10": zeros, "q50": zeros, "q90": zeros}, {}, warnings

    strategy = STRATEGIES[strategy_name]
    overrides = dict(overrides or {})
    profile = _build_profile(history)
    warnings: list[str] = []
    if known_promo is None or known_holiday is None:
        promo, holiday, flag_warnings = _event_flags(history, dates, strategy, overrides)
        warnings.extend(flag_warnings)
    else:
        promo = np.asarray(known_promo, dtype=bool)
        holiday = np.asarray(known_holiday, dtype=bool)

    price_multiplier, price_warnings = _price_multiplier(history, profile, overrides)
    warnings.extend(price_warnings)

    day_levels = np.array([profile["dow_levels"][int(day)] for day in dates.dayofweek], dtype=float)
    progress = (np.arange(len(dates), dtype=float) + 1.0) / max(len(dates), 1)
    trend = 1.0 + (profile["trend_ratio"] - 1.0) * float(strategy["trend_strength"]) * progress
    event_multiplier = np.where(promo, profile["promo_uplift"], 1.0)
    event_multiplier *= np.where(holiday, profile["holiday_uplift"], 1.0)
    event_multiplier = np.clip(event_multiplier, 1.0, 3.5)

    q50 = day_levels * trend * event_multiplier * price_multiplier
    spread_scale = np.sqrt(event_multiplier)
    q10 = q50 + profile["lower_error"] * spread_scale
    q90 = q50 + profile["upper_error"] * spread_scale
    cap = float(profile["sanity_cap"])
    q50 = np.clip(q50, 0.0, cap)
    q10 = np.minimum(np.clip(q10, 0.0, cap), q50)
    q90 = np.maximum(np.clip(q90, 0.0, cap), q50)
    return {"q10": q10, "q50": q50, "q90": q90}, profile, _dedupe_warnings(warnings)


def _quality_for_product(history: pd.DataFrame, forecast_start: pd.Timestamp) -> dict[str, Any]:
    first_date = history["sale_date"].min()
    last_date = history["sale_date"].max()
    span = max((last_date - first_date).days + 1, 1)
    completeness = min(len(history) / span, 1.0)
    oos_rate = float(history["was_oos_recovered"].mean())
    stale_days = max((forecast_start - last_date).days, 0)
    score = 40.0 * min(len(history) / 365.0, 1.0)
    score += 20.0 * completeness
    score += 15.0 * (1.0 - oos_rate)
    score += 25.0 * max(0.0, 1.0 - stale_days / 90.0)
    score = float(np.clip(score, 0.0, 100.0))
    grade = "high" if score >= 85 else "medium" if score >= 65 else "low"
    return {
        "score": round(score, 1),
        "grade": grade,
        "history_days": int(len(history)),
        "completeness_pct": round(completeness * 100.0, 1),
        "oos_rate_pct": round(oos_rate * 100.0, 1),
        "staleness_days": int(stale_days),
        "interval": "empirical robust 10-90",
    }


def forecast_product(
    product_id: int,
    inventory_data: Mapping[str, Any] | None = None,
    *,
    horizon: int = FORECAST_HORIZON,
    overrides: Mapping[str, Any] | None = None,
    strategy: str = "standard",
    initial_stock: float | None = None,
) -> dict[str, Any]:
    """Create a robust daily forecast for one existing SKU."""
    if horizon < 1 or horizon > 366:
        raise ValueError("horizon must be between 1 and 366 days.")
    data = dict(inventory_data) if inventory_data is not None else load_inventory_data()
    products = data["products"]
    try:
        normalized_id = int(product_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("product_id must be an integer.") from exc
    product_rows = products.loc[products["id"] == normalized_id]
    if product_rows.empty:
        raise ValueError(f"Unknown product_id: {normalized_id}")
    product = product_rows.iloc[0]
    history = data["sales"].loc[data["sales"]["product_id"] == normalized_id].copy()
    today = pd.Timestamp.now().normalize()
    last_sale = (
        history["sale_date"].max().normalize()
        if not history.empty
        else pd.Timestamp(data["data_as_of"]).normalize()
    )
    forecast_start = max(today, last_sale + pd.Timedelta(days=1))
    dates = pd.date_range(forecast_start, periods=horizon, freq="D")
    projection, profile, warnings = _project_dates(history, dates, strategy, overrides)

    stale_days = max((today - last_sale).days, 0)
    if stale_days > STALE_AFTER_DAYS:
        warnings.append(
            f"Данные о продажах устарели на {stale_days} дней (последняя дата: {last_sale.date().isoformat()})."
        )
    if profile.get("promo_samples", 0) < 3:
        warnings.append("Промо-эффект принят нейтральным: недостаточно фактических промо-наблюдений.")
    if profile.get("holiday_samples", 0) < 3:
        warnings.append("Праздничный эффект принят нейтральным: недостаточно фактических наблюдений.")

    on_hand = max(_as_float(product["current_quantity"] if initial_stock is None else initial_stock), 0.0)
    stock = np.maximum(on_hand - np.cumsum(projection["q50"]), 0.0)
    safety_stock = np.maximum(projection["q90"] - projection["q50"], 0.0)
    selected_quantile = STRATEGIES[strategy]["quantile"]
    quality = _quality_for_product(history, forecast_start) if not history.empty else {
        "score": 0.0,
        "grade": "low",
        "history_days": 0,
        "completeness_pct": 0.0,
        "oos_rate_pct": 0.0,
        "staleness_days": int(stale_days),
        "interval": "unavailable",
    }

    rounded = {name: np.round(values.astype(float), 3).tolist() for name, values in projection.items()}
    return {
        "product_id": normalized_id,
        "product_name": str(product["name"]),
        "category": str(product["category"]),
        "dates": [date.date().isoformat() for date in dates],
        "demand": rounded["q50"],
        "q10": rounded["q10"],
        "q50": rounded["q50"],
        "q90": rounded["q90"],
        "stock": np.round(stock, 3).tolist(),
        "safety_stock": np.round(safety_stock, 3).tolist(),
        "selected_quantile": selected_quantile,
        "selected_demand": rounded[selected_quantile],
        "forecast_start": dates[0].date().isoformat(),
        "forecast_end": dates[-1].date().isoformat(),
        "data_as_of": last_sale.date().isoformat(),
        "model": MODEL_NAME,
        "quality": quality,
        "warnings": _dedupe_warnings([*data.get("warnings", []), *warnings]),
        "diagnostics": {
            "promo_uplift": round(_as_float(profile.get("promo_uplift"), 1.0), 3),
            "holiday_uplift": round(_as_float(profile.get("holiday_uplift"), 1.0), 3),
            "trend_ratio": round(_as_float(profile.get("trend_ratio"), 1.0), 3),
            "sanity_cap": round(_as_float(profile.get("sanity_cap")), 3),
        },
    }


def evaluate_baseline(
    inventory_data: Mapping[str, Any] | None = None,
    *,
    holdout_days: int = 28,
) -> dict[str, Any]:
    """Fast recent-date holdout evaluation across all SKUs."""
    if holdout_days < 7:
        raise ValueError("holdout_days must be at least 7.")
    data = dict(inventory_data) if inventory_data is not None else load_inventory_data()
    sales = data["sales"].sort_values(["sale_date", "product_id"], kind="stable")
    unique_dates = np.sort(sales["sale_date"].unique())
    if len(unique_dates) < holdout_days + 28:
        holdout_days = max(7, min(holdout_days, len(unique_dates) // 3))
    holdout_dates = unique_dates[-holdout_days:]
    holdout_start = pd.Timestamp(holdout_dates[0])
    train = sales.loc[sales["sale_date"] < holdout_start]
    test = sales.loc[sales["sale_date"] >= holdout_start]

    actual_parts: list[np.ndarray] = []
    q10_parts: list[np.ndarray] = []
    q50_parts: list[np.ndarray] = []
    q90_parts: list[np.ndarray] = []
    evaluated_skus = 0
    for product_id, test_group in test.groupby("product_id", sort=False, observed=True):
        history = train.loc[train["product_id"] == product_id]
        if len(history) < 28:
            continue
        test_group = test_group.sort_values("sale_date", kind="stable")
        dates = pd.DatetimeIndex(test_group["sale_date"])
        projection, _, _ = _project_dates(
            history,
            dates,
            "standard",
            known_promo=test_group["is_promo"].to_numpy(dtype=bool),
            known_holiday=test_group["is_holiday"].to_numpy(dtype=bool),
        )
        actual_parts.append(test_group["recovered_demand"].to_numpy(dtype=float))
        q10_parts.append(projection["q10"])
        q50_parts.append(projection["q50"])
        q90_parts.append(projection["q90"])
        evaluated_skus += 1

    if not actual_parts:
        raise ValueError("Not enough history to evaluate the baseline.")
    actual = np.concatenate(actual_parts)
    q10 = np.concatenate(q10_parts)
    predicted = np.concatenate(q50_parts)
    q90 = np.concatenate(q90_parts)
    denominator = max(float(actual.sum()), 1e-9)
    error = predicted - actual
    coverage = np.mean((actual >= q10) & (actual <= q90)) * 100.0
    wape = round(float(np.abs(error).sum() / denominator * 100.0), 2)
    bias = round(float(error.sum() / denominator * 100.0), 2)
    coverage = round(float(coverage), 2)
    return {
        "wape": wape,
        "wape_pct": wape,
        "mae": round(float(np.mean(np.abs(error))), 2),
        "bias": bias,
        "bias_pct": bias,
        "coverage": coverage,
        "coverage_pct": coverage,
        "holdout_days": int(len(holdout_dates)),
        "holdout_start": pd.Timestamp(holdout_dates[0]).date().isoformat(),
        "holdout_end": pd.Timestamp(holdout_dates[-1]).date().isoformat(),
        "observations": int(actual.size),
        "sku_count": int(evaluated_skus),
        "model": MODEL_NAME,
    }


def _stockout_date(forecast: Mapping[str, Any], available: float) -> str | None:
    cumulative = np.cumsum(np.asarray(forecast["q50"], dtype=float))
    indices = np.flatnonzero(cumulative > available)
    return forecast["dates"][int(indices[0])] if indices.size else None


def build_report_document(report_type: str = "standard") -> dict[str, Any]:
    """Build the renderer-neutral source of truth for PDF and PPTX reports."""
    report_type = str(report_type).lower().strip()
    if report_type not in STRATEGIES:
        raise ValueError(f"Unknown report type: {report_type}. Expected one of: {', '.join(STRATEGIES)}")

    data = load_inventory_data()
    products = data["products"]
    metrics = evaluate_baseline(data)
    strategy = STRATEGIES[report_type]
    actions: list[dict[str, Any]] = []
    warnings = list(data.get("warnings", []))

    for product in products.itertuples(index=False):
        forecast = forecast_product(int(product.id), data, strategy=report_type)
        warnings.extend(forecast["warnings"])
        lead_time = min(max(int(product.lead_time), 1), FORECAST_HORIZON)
        if int(product.lead_time) > FORECAST_HORIZON:
            warnings.append(
                f"Срок поставки товара {int(product.id)} превышает {FORECAST_HORIZON} дней и ограничен горизонтом."
            )
        selected_quantile = str(strategy["quantile"])
        lead_demand = float(np.sum(np.asarray(forecast[selected_quantile], dtype=float)[:lead_time]))
        median_lead_demand = float(np.sum(np.asarray(forecast["q50"], dtype=float)[:lead_time]))
        upper_lead_demand = float(np.sum(np.asarray(forecast["q90"], dtype=float)[:lead_time]))
        on_hand = max(_as_float(product.current_quantity), 0.0)
        in_transit = max(_as_float(product.in_transit_quantity), 0.0)
        available = on_hand + in_transit
        order_quantity = int(math.ceil(max(lead_demand - available, 0.0)))
        daily_median = max(float(np.mean(forecast["q50"])), 1e-9)
        days_cover = available / daily_median
        stockout = _stockout_date(forecast, available)
        action_label = "ЗАКАЗ" if order_quantity > 0 else "КОНТРОЛЬ"
        priority_score = order_quantity * max(_as_float(product.unit_price), 1.0)
        if stockout:
            priority_score += 1_000_000.0

        actions.append(
            {
                "product_id": int(product.id),
                "product_name": str(product.name),
                "category": str(product.category),
                "lead_time_days": int(product.lead_time),
                "on_hand": round(on_hand, 2),
                "in_transit": round(in_transit, 2),
                "unit_price": round(_as_float(product.unit_price), 2),
                "selected_quantile": selected_quantile,
                "lead_time_demand": round(lead_demand, 2),
                "median_lead_time_demand": round(median_lead_demand, 2),
                "safety_stock": round(max(upper_lead_demand - median_lead_demand, 0.0), 2),
                "order_quantity": order_quantity,
                "order_value": round(order_quantity * _as_float(product.unit_price), 2),
                "forecast_30_q10": round(float(np.sum(forecast["q10"])), 2),
                "forecast_30_q50": round(float(np.sum(forecast["q50"])), 2),
                "forecast_30_q90": round(float(np.sum(forecast["q90"])), 2),
                "days_cover": round(days_cover, 1),
                "stockout_date": stockout,
                "action": action_label,
                "priority_score": round(priority_score, 2),
                "quality": forecast["quality"],
                "forecast": {
                    "dates": forecast["dates"],
                    "q10": forecast["q10"],
                    "q50": forecast["q50"],
                    "q90": forecast["q90"],
                },
            }
        )

    if len(actions) != len(products):
        raise RuntimeError("Not every SKU was included in the report document.")
    actions.sort(key=lambda item: (-item["priority_score"], -item["order_quantity"], item["product_id"]))

    category_summaries: list[dict[str, Any]] = []
    for category in sorted({item["category"] for item in actions}):
        group = [item for item in actions if item["category"] == category]
        category_summaries.append(
            {
                "category": category,
                "sku_count": len(group),
                "on_hand": round(sum(item["on_hand"] for item in group), 2),
                "in_transit": round(sum(item["in_transit"] for item in group), 2),
                "forecast_30_q10": round(sum(item["forecast_30_q10"] for item in group), 2),
                "forecast_30_q50": round(sum(item["forecast_30_q50"] for item in group), 2),
                "forecast_30_q90": round(sum(item["forecast_30_q90"] for item in group), 2),
                "order_quantity": int(sum(item["order_quantity"] for item in group)),
                "order_value": round(sum(item["order_value"] for item in group), 2),
                "at_risk_skus": sum(item["stockout_date"] is not None for item in group),
            }
        )

    data_as_of = pd.Timestamp(data["data_as_of"])
    today = pd.Timestamp.now().normalize()
    stale_days = max((today - data_as_of).days, 0)
    warnings = _dedupe_warnings(warnings)

    total_on_hand_value = sum(item["on_hand"] * item["unit_price"] for item in actions)
    total_demand = sum(item["forecast_30_q50"] for item in actions)
    quality_scores = [item["quality"]["score"] for item in actions]
    completeness = float(
        np.mean([item["quality"]["completeness_pct"] for item in actions])
    ) if actions else 0.0
    quality_score = float(np.clip(np.mean(quality_scores) if quality_scores else 0.0, 0.0, 100.0))
    quality_grade = "high" if quality_score >= 85 else "medium" if quality_score >= 65 else "low"

    now = datetime.now(timezone.utc)
    report_id = f"RAY-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    return {
        "report_id": report_id,
        "report_type": report_type,
        "strategy": {**strategy, "name": report_type},
        "metadata": {
            "report_id": report_id,
            "generated_at": now.isoformat(timespec="seconds"),
            "data_as_of": data["data_as_of"],
            "forecast_start": actions[0]["forecast"]["dates"][0] if actions else None,
            "forecast_end": actions[0]["forecast"]["dates"][-1] if actions else None,
            "model": MODEL_NAME,
            "horizon_days": FORECAST_HORIZON,
            "sku_count": len(actions),
            "category_count": len(category_summaries),
            "currency": "KZT",
            "staleness_days": stale_days,
        },
        "metrics": metrics,
        "portfolio": {
            "sku_count": len(actions),
            "at_risk_skus": sum(item["stockout_date"] is not None for item in actions),
            "order_skus": sum(item["order_quantity"] > 0 for item in actions),
            "forecast_30_q50": round(total_demand, 2),
            "forecast_30_q90": round(sum(item["forecast_30_q90"] for item in actions), 2),
            "on_hand_value": round(total_on_hand_value, 2),
            "recommended_order_units": int(sum(item["order_quantity"] for item in actions)),
            "recommended_order_value": round(sum(item["order_value"] for item in actions), 2),
        },
        "warnings": warnings,
        "product_actions": actions,
        "category_summaries": category_summaries,
        "quality": {
            "score": round(quality_score, 1),
            "grade": quality_grade,
            "average_completeness_pct": round(completeness, 1),
            "oos_rows_recovered": int(data["sales"]["was_oos_recovered"].sum()),
            "holdout_coverage_pct": metrics["coverage_pct"],
            "freshness_days": stale_days,
            "checks": {
                "all_skus_included": len(actions) == len(products),
                "quantiles_ordered": all(
                    np.all(np.asarray(item["forecast"]["q10"]) <= np.asarray(item["forecast"]["q50"]))
                    and np.all(np.asarray(item["forecast"]["q50"]) <= np.asarray(item["forecast"]["q90"]))
                    for item in actions
                ),
                "stock_non_negative": True,
                "date_holdout_without_split": True,
            },
        },
    }
