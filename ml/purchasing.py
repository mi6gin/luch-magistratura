"""Deterministic purchasing constraints shared by planning and simulation."""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd


def purchase_settings(product: Mapping) -> dict:
    lead = int(product.get("lead_time", 1))
    result = {}
    for key, default, minimum in (
        ("minimum_order_quantity", 1, 1), ("pack_size", 1, 1),
        ("target_cover_days", lead, 1), ("safety_stock_days", 0, 0),
    ):
        value = product.get(key, default)
        if value is None or pd.isna(value):
            value = default
        number = float(value)
        if not math.isfinite(number) or number != int(number) or number < minimum:
            raise ValueError(f"Некорректная настройка закупки: {key}.")
        result[key] = int(number)
    flag = product.get("replenishable", True)
    if flag is None or pd.isna(flag):
        flag = True
    if flag not in (True, False, 0, 1):
        raise ValueError("Некорректная настройка закупки: replenishable.")
    result["replenishable"] = bool(flag)
    # Daily review requires at least one day of demand after the new order arrives.
    result["coverage_days"] = max(lead + 1, result["target_cover_days"]) + result["safety_stock_days"]
    if not 1 <= lead <= 365 or result["coverage_days"] > 366:
        raise ValueError("Период закупки превышает поддерживаемые 366 дней.")
    return result


def round_order(shortfall: float, minimum: int, pack: int) -> int:
    if shortfall <= 1e-9:
        return 0
    return int(math.ceil(max(shortfall, minimum) / pack) * pack)


def stock_freshness(product: Mapping, as_of=None, maximum_age_days: int = 7) -> dict:
    today = pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.now().normalize()
    snapshot = pd.to_datetime(product.get("stock_as_of"), errors="coerce")
    if pd.isna(snapshot):
        return {"stock_as_of": None, "stock_staleness_days": None, "stock_fresh": False,
                "stock_warning": "Дата остатков неизвестна: обновите остатки перед закупкой."}
    age = (today - snapshot.normalize()).days
    fresh = 0 <= age <= maximum_age_days
    return {"stock_as_of": snapshot.date().isoformat(), "stock_staleness_days": age,
            "stock_fresh": fresh,
            "stock_warning": None if fresh else "Дата остатков устарела или находится в будущем: обновите остатки перед закупкой."}


def plan_order(product: Mapping, forecast: Mapping, *, as_of=None) -> dict:
    settings = purchase_settings(product)
    freshness = stock_freshness(product, as_of)
    count = settings["coverage_days"]
    lead = int(product.get("lead_time", 1))
    if len(forecast["q50"]) < count:
        raise ValueError("Прогноз короче периода закупки.")
    selected = str(forecast["selected_quantile"])
    demand = np.asarray(forecast[selected], dtype=float)[:count]
    median = np.asarray(forecast["q50"], dtype=float)[:count]
    receipts = np.asarray(forecast["receipts"], dtype=float)[:count]
    on_hand = float(product.get("current_quantity", 0))
    # Lost sales before a future receipt must not consume that receipt twice.
    # A new regular order arrives at index `lead`; earlier deficits need expediting.
    balances = on_hand + np.cumsum(receipts - demand)
    shortage_before_arrival = bool(np.any(balances[:lead] < -1e-9))
    remaining = on_hand
    for i in range(min(lead, count)):
        remaining = max(remaining + receipts[i] - demand[i], 0.0)
    after_arrival = remaining + np.cumsum(receipts[lead:] - demand[lead:])
    shortfall = max(float(-after_arrival.min()), 0.0)
    proposed = round_order(shortfall, settings["minimum_order_quantity"], settings["pack_size"])
    if not settings["replenishable"]:
        status, quantity = "disabled", 0
    elif not freshness["stock_fresh"]:
        status, quantity = "refresh_stock", 0
    else:
        status, quantity = "order" if proposed else "monitor", proposed
    return {**settings, **freshness, "order_status": status, "order_quantity": quantity,
            "proposed_order_quantity": proposed, "expedite_required": shortage_before_arrival,
            "expedite_quantity": round(max(float(-balances[:lead].min()), 0.0), 3),
            "coverage_demand": round(float(demand.sum()), 3),
            "configured_safety_stock": round(float(median[-settings["safety_stock_days"]:].sum()), 3) if settings["safety_stock_days"] else 0.0}
