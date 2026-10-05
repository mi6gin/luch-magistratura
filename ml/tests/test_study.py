import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ml.research.data import prepare_uci_online_retail
from ml.research.study import run_job, write


class CohortTests(unittest.TestCase):
    def transactions(self, future_quantity=1):
        dates = pd.date_range("2020-01-01", periods=400)
        rows = [
            {"Invoice": str(day), "StockCode": str(10000 + sku), "Description": "product",
             "Quantity": 1 if day < 316 else future_quantity, "InvoiceDate": date,
             "Price": 2, "Country": "United Kingdom"}
            for sku in range(8) for day, date in enumerate(dates)
            if (day < 316 and day % (1 + sku % 3) == 0)
            or (day >= 316 and future_quantity > 1 and sku % 2 == 0) or day == 399
        ]
        rows.extend({"Invoice": f"new-{day}", "StockCode": "10009", "Description": "future-only product",
                     "Quantity": 1, "InvoiceDate": dates[day], "Price": 2, "Country": "United Kingdom"}
                    for day in range(316, 400))
        return pd.DataFrame(rows)

    def test_cohort_uses_training_only_and_excludes_pilot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.xlsx"
            source.touch()
            selected = []
            for index, quantity in enumerate((1, 100000)):
                with patch("ml.research.data.pd.read_excel", return_value={"sheet": self.transactions(quantity)}):
                    manifest = prepare_uci_online_retail(source, root / str(index), 4,
                                                        selection_cutoff="2020-11-11", exclude_series={"10000"})
                data = pd.read_csv(root / str(index) / manifest.files["data"], dtype={"id": str})
                selected.append(set(data["id"]))
                self.assertNotIn("10000", selected[-1])
                self.assertNotIn("10009", selected[-1])
                self.assertEqual(manifest.preprocessing["excluded_pilot_series"], "1")
            self.assertEqual(selected[0], selected[1])

    def test_late_selection_cutoff_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.xlsx"
            source.touch()
            with patch("ml.research.data.pd.read_excel", return_value={"sheet": self.transactions()}):
                with self.assertRaisesRegex(ValueError, "training period"):
                    prepare_uci_online_retail(source, Path(directory) / "out", selection_cutoff="2021-01-01")


class FrozenStudyTests(unittest.TestCase):
    def test_completed_job_resumes_without_launching_and_config_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "results" / "one.json", {"completed": True})
            with patch("ml.research.study.subprocess.run") as launcher:
                result = run_job(root, "one", root / "data", root / "manifest", "gru", {"seed": 42})
                self.assertTrue(result["completed"])
                launcher.assert_not_called()
                with self.assertRaisesRegex(ValueError, "Frozen job changed"):
                    run_job(root, "one", root / "data", root / "manifest", "gru", {"seed": 43})


if __name__ == "__main__":
    unittest.main()
