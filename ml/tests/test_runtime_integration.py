from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecasting import (
    _project_dates, _stockout_date, build_report_document, evaluate_active_model,
    evaluate_baseline, forecast_product, load_inventory_data,
)
from predict_cli import run_planning, run_simulate
from runtime_model import resolve_runtime_model
from runtime_policy import apply_active_policy


@contextmanager
def active_policy(route="moving_median_28 × 1.5", routes=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        artifact = root / "models" / "manifest.json"
        artifact.parent.mkdir()
        artifact.write_text(json.dumps({
            "runtime": "local-demand-router-v1",
            "routes": routes if routes is not None else {
                label: route for label in ("smooth", "intermittent", "erratic", "lumpy")
            },
        }), encoding="utf-8")
        registry = root / "registry.json"
        registry.write_text(json.dumps({
            "production_id": "policy", "models": [{
                "id": "policy", "name": "local-demand-router-v1", "status": "production",
                "artifact_path": str(artifact),
            }],
        }), encoding="utf-8")
        with patch.dict("os.environ", {
            "ML_MODEL_REGISTRY_PATH": str(registry), "ML_MODELS_PATH": str(artifact.parent),
        }):
            yield registry


def inventory(scenario_history=False):
    dates = pd.date_range(end=pd.Timestamp.now().normalize() - pd.Timedelta(days=1), periods=140)
    index = np.arange(len(dates))
    promo = (index % 28 >= 15) & (index % 28 <= 17) if scenario_history else np.zeros(140, dtype=bool)
    prices = np.take([80, 100, 120, 150], index % 4) if scenario_history else np.repeat(100, 140)
    demand = (
        (40 + dates.dayofweek.to_numpy() * 2) * np.where(index >= 112, 1.25, 1)
        * np.where(promo, 1.8, 1) * 100 / prices
    ) if scenario_history else np.repeat(10.0, 140)
    sales = pd.DataFrame({
        "product_id": 1, "sale_date": dates, "quantity_sold": demand,
        "recovered_demand": demand, "in_stock": True, "is_promo": promo,
        "is_holiday": False, "was_oos_recovered": False, "sale_price": prices,
    })
    return {
        "sales": sales, "products": pd.DataFrame([{
            "id": 1, "sku": "SKU-1", "name": "Test", "category": "Test",
            "lead_time": 7, "unit_price": 100, "current_quantity": 10,
            "in_transit_quantity": 0,
        }]), "transit": pd.DataFrame(), "data_as_of": dates[-1].date().isoformat(), "warnings": [],
    }


class RuntimeIntegrationTest(unittest.TestCase):
    def test_policy_preserves_price_promo_trend_and_seasonal_scenarios(self):
        data = inventory(scenario_history=True)
        overrides = {"is_promo": 0, "is_holiday": 0}
        for route in ("moving_median_28", "croston_sba", "seasonal_naive_7"):
            with self.subTest(route=route), active_policy(route):
                neutral = forecast_product(1, data, overrides=overrides)
                promo = forecast_product(1, data, overrides={**overrides, "is_promo": 1})
                price = forecast_product(1, data, overrides={**overrides, "price_change": 0.2})
                trend = forecast_product(1, data, strategy="trend", overrides=overrides)
                campaign = forecast_product(1, data, strategy="promo", overrides={"is_holiday": 0})
            self.assertEqual(neutral["model"], "local-demand-router-v1")
            self.assertGreater(np.mean(promo["q50"]), np.mean(neutral["q50"]) * 1.3)
            self.assertLess(np.mean(price["q50"]), np.mean(neutral["q50"]))
            self.assertGreater(np.mean(trend["q50"]), np.mean(neutral["q50"]))
            self.assertGreater(np.mean(campaign["q50"][:7]), np.mean(neutral["q50"][:7]) * 1.3)
            self.assertGreater(np.ptp(neutral["q50"][:7]), 2)
            for forecast in (neutral, promo, price, trend, campaign):
                self.assertTrue(np.all(np.asarray(forecast["q10"]) <= forecast["q50"]))
                self.assertTrue(np.all(np.asarray(forecast["q50"]) <= forecast["q90"]))

    def test_holdout_and_cli_metrics_use_the_actual_active_model(self):
        data = inventory()
        with active_policy(), patch("forecasting.load_inventory_data", return_value=data):
            baseline = evaluate_baseline(data)
            active = evaluate_active_model(data)
            planning = run_planning()
        self.assertEqual(baseline["wape_pct"], 0)
        self.assertEqual(active["wape_pct"], 50)
        self.assertEqual(active["model"], "local-demand-router-v1")
        self.assertEqual(planning["model"], active["model"])
        self.assertEqual(planning["evaluation"]["model"], active["model"])
        self.assertEqual(planning["evaluation"]["wape_pct"], active["wape_pct"])

    def test_missing_route_cli_labels_the_fallback_forecast_correctly(self):
        with active_policy(routes={}), patch("predict_cli.load_inventory_data", return_value=inventory()):
            simulation = run_simulate(1)
        self.assertEqual(simulation["model"], "seasonal-robust-v1")
        self.assertTrue(simulation["warnings"])

    def test_resolve_explicit_registry_does_not_load_a_different_environment_registry(self):
        with active_policy() as registry, patch.dict("os.environ", {"ML_MODEL_REGISTRY_PATH": "missing.json"}):
            self.assertEqual(resolve_runtime_model(registry), ("local-demand-router-v1", None))

    def test_late_transit_cannot_hide_stockout_or_reduce_lead_time_order(self):
        data = inventory()
        arrival = pd.Timestamp.now().normalize() + pd.Timedelta(days=14)
        data["transit"] = pd.DataFrame([{"product_id": 1, "in_transit_quantity": 1000, "expected_date": arrival}])
        data["products"]["in_transit_quantity"] = 1000
        with patch.dict("os.environ", {"ML_MODEL_REGISTRY_PATH": ""}), patch("forecasting.load_inventory_data", return_value=data):
            forecast = forecast_product(1, data)
            action = build_report_document()["product_actions"][0]
        self.assertEqual(forecast["receipts"][:14], [0] * 14)
        self.assertEqual(forecast["receipts"][14], 1000)
        self.assertEqual(forecast["stock"][1], 0)
        self.assertEqual(forecast["stock"][14], 990)
        self.assertEqual(_stockout_date(forecast, 10), forecast["dates"][1])
        self.assertEqual(action["order_quantity"], 60)
        self.assertEqual(action["in_transit_within_lead_time"], 0)
        self.assertIsNotNone(action["stockout_date"])

    def test_timely_transit_prevents_stockout_and_undated_transit_does_not(self):
        data = inventory()
        tomorrow = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
        data["transit"] = pd.DataFrame([{"product_id": 1, "in_transit_quantity": 1000, "expected_date": tomorrow}])
        with patch.dict("os.environ", {"ML_MODEL_REGISTRY_PATH": ""}):
            timely = forecast_product(1, data)
            data["transit"]["expected_date"] = None
            unknown = forecast_product(1, data)
        self.assertIsNone(_stockout_date(timely, 10))
        self.assertIsNotNone(_stockout_date(unknown, 10))
        self.assertEqual(sum(unknown["receipts"]), 0)
        self.assertTrue(any("Поставка" in warning for warning in unknown["warnings"]))

    def test_inventory_loader_keeps_each_transit_date_and_closes_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "inventory.db"
            connection = sqlite3.connect(database)
            with connection:
                connection.executescript("""
                    CREATE TABLE products (id INTEGER, name TEXT, category TEXT, lead_time INTEGER, unit_price REAL);
                    INSERT INTO products VALUES (1, 'Test', 'Test', 7, 100);
                    CREATE TABLE sales_history (product_id INTEGER, sale_date TEXT, quantity_sold REAL);
                    INSERT INTO sales_history VALUES (1, '2026-10-01', 10);
                    CREATE TABLE warehouse_stock (product_id INTEGER, current_quantity REAL);
                    INSERT INTO warehouse_stock VALUES (1, 10);
                    CREATE TABLE warehouse_in_transit (product_id INTEGER, in_transit_quantity REAL, expected_date TEXT);
                    INSERT INTO warehouse_in_transit VALUES (1, 20, '2027-01-01'), (1, 30, '2027-02-01');
                """)
            connection.close()
            loaded = load_inventory_data(database)
            self.assertEqual(loaded["products"].iloc[0]["in_transit_quantity"], 50)
            self.assertEqual(len(loaded["transit"]), 2)
            self.assertEqual(loaded["transit"]["expected_date"].nunique(), 2)
            database.unlink()  # Regression: sqlite context manager alone leaks handles on Windows.

    def test_holdout_does_not_score_censored_or_future_imputed_sales(self):
        data = inventory()
        sales = data["sales"]
        sales.loc[sales.index[-28:], "recovered_demand"] = 1000
        sales.loc[sales.index[-7:], "in_stock"] = False
        result = evaluate_baseline(data)
        self.assertEqual(result["wape_pct"], 0)
        self.assertEqual(result["observations"], 21)
        self.assertEqual(result["evaluation_target"], "observed-in-stock-sales")

    def test_censoring_holdout_targets_does_not_change_retained_date_forecasts(self):
        for evaluator in (evaluate_baseline, evaluate_active_model):
            with self.subTest(evaluator=evaluator.__name__), active_policy("moving_median_28"):
                data = inventory()
                demand = np.linspace(10, 100, len(data["sales"]))
                data["sales"]["quantity_sold"] = demand
                data["sales"]["recovered_demand"] = demand
                baseline_projections, active_projections = [], []

                def capture_baseline(*args, **kwargs):
                    result = _project_dates(*args, **kwargs)
                    baseline_projections.append({name: values.copy() for name, values in result[0].items()})
                    return result

                def capture_active(*args, **kwargs):
                    result = apply_active_policy(*args, **kwargs)
                    active_projections.append({name: values.copy() for name, values in result[0].items()})
                    return result

                with patch("forecasting._project_dates", side_effect=capture_baseline), patch(
                    "forecasting.apply_active_policy", side_effect=capture_active,
                ):
                    full = evaluator(data)
                    data["sales"].loc[data["sales"].index[-7:], "in_stock"] = False
                    censored = evaluator(data)

                self.assertEqual(full["observations"], 28)
                self.assertEqual(censored["observations"], 21)
                projections = active_projections if evaluator is evaluate_active_model else baseline_projections
                for quantile in ("q10", "q50", "q90"):
                    self.assertEqual(len(projections[1][quantile]), 28)
                    np.testing.assert_array_equal(projections[0][quantile][:21], projections[1][quantile][:21])
                predicted = projections[0]["q50"][:21]
                actual = demand[-28:-7]
                self.assertEqual(censored["wape_pct"], round(float(np.abs(predicted - actual).sum() / actual.sum() * 100), 2))


if __name__ == "__main__":
    unittest.main()
