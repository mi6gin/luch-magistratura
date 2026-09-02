from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.data import prepare_local_inventory, prepare_m5, prepare_uci_online_retail, select_series, temporal_boundaries
from research.dataset import FEATURES, normalize_from_train
from research.metrics import demand_type, interval_coverage, point_metrics, quantiles_are_ordered
from research.experiment import _aggregate, _croston_sba, _fold_manifest, adaptive_baseline, risk_calibrated_baseline, seasonal_baseline


class ResearchPipelineTest(unittest.TestCase):
    def test_metrics_have_expected_meaning(self):
        actual = np.array([10, 20, 30])
        predicted = np.array([12, 18, 33])
        metrics = point_metrics(actual, predicted)
        self.assertAlmostEqual(metrics["wape_pct"], 11.6667)
        self.assertAlmostEqual(metrics["mae"], 2.3333)
        self.assertAlmostEqual(metrics["bias_pct"], 5.0)
        self.assertAlmostEqual(metrics["underforecast_pct"], 3.3333)
        self.assertAlmostEqual(metrics["risk_cost_pct"], 15.0)
        self.assertEqual(interval_coverage(actual, actual - 1, actual + 1), 100.0)

    def test_quantile_crossing_is_detected(self):
        self.assertTrue(quantiles_are_ordered(np.array([[[1, 2, 3]]])))
        self.assertFalse(quantiles_are_ordered(np.array([[[2, 1, 3]]])))

    def test_weekly_seasonal_baseline_covers_any_horizon(self):
        history = np.zeros((1, 14, 8), dtype=np.float32)
        history[0, -7:, 0] = np.arange(1, 8)
        target = np.tile(np.arange(1, 8), 4).reshape(1, 28).astype(np.float32)
        result = seasonal_baseline((history, target, ["sku"]), {"sku": 1.0})
        self.assertEqual(result["metrics"]["wape_pct"], 0.0)

    def test_rolling_folds_are_ordered_and_aggregated(self):
        manifest = {"date_start": "2020-01-01", "test_end": "2021-12-31"}
        first = _fold_manifest(manifest, 0, 3)
        last = _fold_manifest(manifest, 2, 3)
        self.assertLess(first["test_end"], last["test_end"])
        fold_results = [
            [{"model": "baseline", "metrics": {"wape_pct": value, "mae": 2, "rmse": 3, "bias_pct": 1}}]
            for value in (10, 20, 30)
        ]
        aggregate = _aggregate(fold_results)[0]
        self.assertEqual(aggregate["metrics"]["wape_pct"], 20.0)
        self.assertEqual(aggregate["metrics"]["wape_pct_std"], 10.0)
        self.assertEqual(aggregate["folds_completed"], 3)

    def test_intermittent_demand_is_classified_and_croston_is_positive(self):
        history = np.zeros(90)
        history[[5, 20, 40, 65, 80]] = [4, 6, 5, 7, 6]
        self.assertEqual(demand_type(history), "intermittent")
        self.assertGreater(_croston_sba(history), 0)

    def test_temporal_split_keeps_test_after_validation(self):
        dates = pd.Series(pd.date_range("2024-01-01", periods=220, freq="D"))
        bounds = temporal_boundaries(dates)
        self.assertLess(bounds["train_end"], bounds["validation_end"])
        self.assertLess(bounds["validation_end"], bounds["test_end"])

    def test_series_selection_is_reproducible(self):
        metadata = pd.DataFrame({
            "id": [f"item-{value}" for value in range(30)],
            "dept_id": [f"dept-{value % 3}" for value in range(30)],
            "store_id": [f"store-{value % 2}" for value in range(30)],
        })
        first = select_series(metadata, 12, seed=42)
        second = select_series(metadata, 12, seed=42)
        self.assertEqual(first["id"].tolist(), second["id"].tolist())
        self.assertEqual(first["dept_id"].nunique(), 3)

    def test_normalization_does_not_leak_future_values(self):
        dates = pd.date_range("2024-01-01", periods=12)
        frame = pd.DataFrame({
            "id": ["sku"] * 12,
            "date": dates,
            "sales": [10] * 10 + [10000, 20000],
            "sell_price": [100] * 10 + [9999, 9999],
            "wday": dates.dayofweek + 1,
            "month": dates.month,
            "is_event": [0] * 12,
            "snap": [0] * 12,
        })
        _, scales = normalize_from_train(frame, "2024-01-10")
        self.assertEqual(scales.sales["sku"], 10)
        self.assertEqual(scales.price["sku"], 100)
        normalized, _ = normalize_from_train(frame, "2024-01-10")
        self.assertTrue(set(("sales_mean_7", "nonzero_rate_28", "days_since_sale_scaled")).issubset(FEATURES))
        self.assertAlmostEqual(normalized.iloc[0]["sales_mean_7"], 1.0)

    def test_adaptive_router_uses_validation_without_test_labels(self):
        history = np.zeros((2, 90, len(FEATURES)), dtype=np.float32)
        history[:, :, 0] = 2
        validation_target = np.full((2, 28), 2, dtype=np.float32)
        test_target = np.full((2, 28), 99, dtype=np.float32)
        values = (history, validation_target, ["sku-a", "sku-b"])
        result = adaptive_baseline(values, (history, test_target, ["sku-a", "sku-b"]), {"sku-a": 1, "sku-b": 1})
        self.assertEqual(result["routes"]["smooth"], "seasonal_naive_7")
        self.assertEqual(result["metrics"]["wape_pct"], 97.9798)

    def test_risk_router_calibrates_against_underforecasting(self):
        history = np.zeros((2, 90, len(FEATURES)), dtype=np.float32)
        history[:, :, 0] = 2
        validation_target = np.full((2, 28), 4, dtype=np.float32)
        test_target = np.full((2, 28), 4, dtype=np.float32)
        values = (history, validation_target, ["sku-a", "sku-b"])
        result = risk_calibrated_baseline(values, values, {"sku-a": 1, "sku-b": 1})
        self.assertTrue(result["routes"]["smooth"].endswith("× 2"))
        self.assertEqual(result["metrics"]["underforecast_pct"], 0.0)

    def test_prepare_m5_creates_data_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "raw"
            output = Path(temporary) / "processed"
            raw.mkdir()
            days = 190
            sales_rows = []
            for item in range(4):
                row = {
                    "id": f"item_{item}_store_1_evaluation",
                    "item_id": f"item_{item}",
                    "dept_id": f"dept_{item % 2}",
                    "cat_id": "cat_1",
                    "store_id": "store_1",
                    "state_id": "CA",
                }
                row.update({f"d_{day}": item + day % 7 for day in range(1, days + 1)})
                sales_rows.append(row)
            pd.DataFrame(sales_rows).to_csv(raw / "sales_train_evaluation.csv", index=False)
            calendar = pd.DataFrame({
                "d": [f"d_{day}" for day in range(1, days + 1)],
                "date": pd.date_range("2024-01-01", periods=days),
                "wday": [(day - 1) % 7 + 1 for day in range(1, days + 1)],
                "month": [1] * days,
                "year": [2024] * days,
                "event_name_1": [None] * days,
                "event_type_1": [None] * days,
                "snap_CA": [0] * days,
                "snap_TX": [0] * days,
                "snap_WI": [0] * days,
                "wm_yr_wk": [(day - 1) // 7 + 1 for day in range(1, days + 1)],
            })
            calendar.to_csv(raw / "calendar.csv", index=False)
            prices = [
                {"store_id": "store_1", "item_id": f"item_{item}", "wm_yr_wk": week, "sell_price": 10 + item}
                for item in range(4)
                for week in range(1, 29)
            ]
            pd.DataFrame(prices).to_csv(raw / "sell_prices.csv", index=False)

            manifest = prepare_m5(raw, output, series_limit=3)
            saved = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.series_count, 3)
            self.assertEqual(saved["seed"], 42)
            self.assertEqual(saved["row_count"], 570)
            self.assertTrue((output / "m5_subset.csv.gz").is_file())

    def test_prepare_uci_cleans_transactions_and_creates_daily_series(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "retail.xlsx"
            dates = pd.date_range("2024-01-01", periods=180, freq="D")
            rows = []
            for item in ("10001", "10002"):
                rows.extend({
                    "Invoice": f"INV-{item}-{index}",
                    "StockCode": item,
                    "Description": f"Product {item}",
                    "Quantity": index % 4 + 1,
                    "InvoiceDate": date,
                    "Price": 10.0,
                    "Customer ID": 1,
                    "Country": "United Kingdom",
                } for index, date in enumerate(dates))
            rows.append({
                "Invoice": "C-CANCELLED", "StockCode": "10001", "Description": "Cancelled",
                "Quantity": -100, "InvoiceDate": dates[-1], "Price": 10, "Customer ID": 1,
                "Country": "United Kingdom",
            })
            frame = pd.DataFrame(rows)
            with pd.ExcelWriter(source, engine="openpyxl") as writer:
                frame.iloc[:180].to_excel(writer, sheet_name="Year 1", index=False)
                frame.iloc[180:].to_excel(writer, sheet_name="Year 2", index=False)

            manifest = prepare_uci_online_retail(source, root / "processed", series_limit=2)
            prepared = pd.read_csv(root / "processed" / "uci_online_retail_subset.csv.gz")
            self.assertEqual(manifest.series_count, 2)
            self.assertEqual(manifest.row_count, 360)
            self.assertGreater(prepared["sales"].min(), -1)
            self.assertNotIn(-100, prepared["sales"].tolist())

    def test_prepare_local_inventory_reads_sqlite_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "inventory.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, category TEXT, unit_price REAL)")
                connection.execute("CREATE TABLE sales_history (product_id INTEGER, sale_date TEXT, quantity_sold INTEGER, in_stock INTEGER, is_holiday INTEGER, is_promo INTEGER)")
                connection.execute("INSERT INTO products VALUES (1, 'SKU-1', 'Товар', 'Тест', 100)")
                connection.executemany(
                    "INSERT INTO sales_history VALUES (1, ?, ?, 1, 0, 0)",
                    [(date.date().isoformat(), index % 5) for index, date in enumerate(pd.date_range("2024-01-01", periods=200))],
                )
            before = database.read_bytes()
            manifest = prepare_local_inventory(database, root / "output")
            prepared = pd.read_csv(root / "output/local_inventory.csv.gz")
            self.assertEqual(manifest.series_count, 1)
            self.assertEqual(manifest.history_days, 200)
            self.assertEqual(len(prepared), 200)
            self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
