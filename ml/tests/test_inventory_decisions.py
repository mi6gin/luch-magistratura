from __future__ import annotations

import tempfile
import sqlite3
import unittest
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.purchasing import plan_order
from ml.forecasting import load_inventory_data
from ml.inventory_backtest import simulate
from ml.research.runtime_validation import validate_runtime
from ml.research.models import build_model, model_loss, require_torch
from ml.research.trainer import TrainingConfig, train_model, evaluate_model
from ml.research.experiment import run_experiment


class PurchasingTests(unittest.TestCase):
    def plan(self, **overrides):
        product = {"lead_time": 7, "current_quantity": 10, "stock_as_of": "2026-10-31", **overrides}
        forecast = {"q50": np.repeat(10., 30), "receipts": np.zeros(30), "selected_quantile": "q50"}
        return plan_order(product, forecast, as_of="2026-10-31")

    def test_minimum_and_pack_are_applied_together_only_when_needed(self):
        self.assertEqual(self.plan(minimum_order_quantity=100, pack_size=24)["order_quantity"], 120)
        self.assertEqual(self.plan(current_quantity=1000, minimum_order_quantity=100, pack_size=24)["order_quantity"], 0)

    def test_disabled_and_unknown_stale_or_future_stock_cannot_generate_order(self):
        self.assertEqual(self.plan(replenishable=False)["order_status"], "disabled")
        for snapshot in (None, "2000-01-01", "2026-11-01"):
            result = self.plan(stock_as_of=snapshot)
            self.assertEqual(result["order_status"], "refresh_stock")
            self.assertEqual(result["order_quantity"], 0)
            self.assertEqual(result["proposed_order_quantity"], 10)

    def test_future_receipt_does_not_hide_intermediate_shortage(self):
        receipts = np.zeros(14)
        receipts[10] = 140
        result = plan_order({"lead_time": 7, "target_cover_days": 14, "current_quantity": 70,
                             "stock_as_of": "2026-10-31"},
                            {"q50": np.repeat(10., 14), "receipts": receipts, "selected_quantile": "q50"},
                            as_of="2026-10-31")
        self.assertEqual(result["order_quantity"], 30)

    def test_loader_scopes_settings_and_preserves_oldest_stock_date(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"test.db"
            with sqlite3.connect(path) as c:
                c.executescript("""
                    CREATE TABLE products(id INTEGER,name TEXT,category TEXT,lead_time INTEGER,unit_price REAL);
                    INSERT INTO products VALUES(1,'Test','Test',7,100);
                    CREATE TABLE sales_history(product_id INTEGER,sale_date TEXT,quantity_sold REAL);
                    INSERT INTO sales_history VALUES(1,'2026-10-30',10);
                    CREATE TABLE warehouse_stock(product_id INTEGER,current_quantity REAL,as_of_date TEXT,branch_id INTEGER);
                    INSERT INTO warehouse_stock VALUES(1,10,'2000-01-01',1),(1,20,'2026-10-30',1),(1,999,'2026-10-30',2);
                    CREATE TABLE product_planning_settings(product_id INTEGER,branch_id INTEGER,pack_size INTEGER,replenishable INTEGER);
                    INSERT INTO product_planning_settings VALUES(1,1,24,0),(1,2,99,1);
                """)
            c.close()
            product = load_inventory_data(path, branch_id=1)["products"].iloc[0]
            self.assertEqual(product["current_quantity"], 30)
            self.assertEqual(product["pack_size"], 24)
            self.assertEqual(product["replenishable"], 0)
            self.assertEqual(product["stock_as_of"], pd.Timestamp("2000-01-01"))


def daily_frame():
    dates = pd.date_range("2025-01-01", periods=140)
    return pd.DataFrame({"id": "one", "date": dates, "sales": 10., "sell_price": 100.,
                         "in_stock": 1, "snap": 0, "is_event": 0})


class RuntimeValidationTests(unittest.TestCase):
    def test_local_experiment_attaches_evidence_for_latest_routes(self):
        dates = pd.date_range("2025-01-01", periods=400)
        frame = pd.DataFrame({"id": "one", "date": dates, "sales": 10., "sell_price": 100.,
                              "in_stock": 1, "snap": 0, "is_event": 0,
                              "wday": dates.dayofweek + 1, "month": dates.month, "year": dates.year})
        manifest = {"dataset": "Local Rayventory inventory", "date_start": "2025-01-01",
                    "train_end": "2025-09-01", "validation_end": "2025-10-27", "test_end": "2025-11-24"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame.to_csv(root/"data.csv", index=False)
            (root/"manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            experiment = run_experiment(root/"data.csv", root/"manifest.json", root/"out", [], TrainingConfig(), folds=3)
            router = next(row for row in experiment["results"] if row["model"] == "adaptive_demand_router")
            latest = next(row for row in experiment["folds"][-1]["results"] if row["model"] == "adaptive_demand_router")
            self.assertEqual(router["routes"], latest["routes"])
            self.assertEqual(router["runtime_validation"]["routes"], latest["routes"])
            self.assertEqual(router["runtime_validation"]["end"], manifest["test_end"])
            self.assertEqual(router["runtime_validation"]["observations"], 28)

    def test_future_promotions_are_not_used_to_score_deployed_forecast(self):
        frame = daily_frame()
        routes = {key: "moving_median_28" for key in ("smooth", "intermittent", "lumpy", "erratic")}
        first = validate_runtime(frame, routes, "2025-04-23", "2025-05-20")
        frame.loc[frame["date"] >= "2025-04-23", "snap"] = 1
        second = validate_runtime(frame, routes, "2025-04-23", "2025-05-20")
        self.assertEqual(first, second)
        self.assertEqual(first["observations"], 28)
        self.assertEqual(first["metrics"]["wape_pct"], 0)


class InventorySimulationTests(unittest.TestCase):
    def test_simulation_conserves_inventory_and_respects_arrival_delay(self):
        result = simulate(daily_frame(), "2025-04-23", "2025-05-20", initial_stock=0, lead_time=2, review_days=3)
        for row in result["series_results"]:
            self.assertGreaterEqual(row["lost_units"], 20)
            if row["method"] == "seasonal_naive_7":
                self.assertEqual(row["lost_units"], 20)
                self.assertEqual(row["stockout_days"], 2)
            self.assertAlmostEqual(row["ordered_units"], row["served_units"] + row["ending_stock"] + row["ending_in_transit"])

    def test_censored_test_sales_are_rejected_instead_of_used_as_true_demand(self):
        frame = daily_frame()
        frame.loc[frame.index[-1], "in_stock"] = 0
        with self.assertRaisesRegex(ValueError, "uncensored"):
            simulate(frame, "2025-04-23", "2025-05-20", initial_stock=20)


class ZeroDemandModelTests(unittest.TestCase):
    def test_new_checkpoints_train_and_evaluate_on_zero_heavy_targets(self):
        rng = np.random.default_rng(42)
        x = rng.random((16, 8, 2), dtype=np.float32)
        y = np.where(rng.random((16, 3)) < .75, 0., 1.).astype(np.float32)
        values = (x, y, ["one"] * 16)
        with tempfile.TemporaryDirectory() as directory:
            for architecture in ("lstm", "gru", "transformer"):
                output = Path(directory)/architecture
                result = train_model(architecture, values, values, output, TrainingConfig(
                    history_days=8, horizon_days=3, hidden_size=8, batch_size=8, max_epochs=3, patience=3,
                ))
                self.assertEqual(result["quantile_parameterization"], "zero_inflated_lognormal_v3")
                evaluated = evaluate_model(architecture, output/result["weights"], values, {"one": 1.})
                self.assertTrue(np.isfinite(evaluated["wape_pct"]))
                self.assertTrue(evaluated["quantiles_ordered"])

    def test_mixture_can_represent_zero_quantiles_and_learn_from_positive_sales(self):
        torch, _ = require_torch()
        for architecture in ("lstm", "gru", "transformer"):
            model = build_model(architecture, 2, 8, 3, 8)
            with torch.no_grad():
                for parameter in model.parameters():
                    parameter.zero_()
                model.head.bias.copy_(torch.tensor([np.log(.2/.8), 0., 0.] * 3))
            x = torch.zeros(2, 8, 2)
            q = model(x)
            torch.testing.assert_close(q, torch.tensor([[[0., 0., 1.]] * 3] * 2))
            model_loss(model, x, torch.ones(2, 3)).backward()
            self.assertTrue(torch.all(model.head.bias.grad.reshape(3,3)[:,0] < 0))
            self.assertTrue(all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters()))
