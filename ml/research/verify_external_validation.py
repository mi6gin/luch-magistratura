"""Recompute published external-validation metrics from exported observations."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .external_validation import bootstrap_differences, sha
from .metrics import point_metrics


def verify(folder: Path):
    result = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    if sha(folder / "cohort.csv.gz") != result["sha256"]["cohort"]:
        raise AssertionError("Cohort checksum mismatch")
    if sha(folder / "protocol.json") != result["sha256"]["protocol"]:
        raise AssertionError("Protocol checksum mismatch")
    cohort = pd.read_csv(folder / "cohort.csv.gz", parse_dates=["date"])
    if cohort.duplicated(["id", "date"]).any():
        raise AssertionError("Duplicate item/date")
    forecasts = pd.read_csv(folder / "forecast-test.csv.gz")
    truth = cohort.assign(date=cohort.date.dt.strftime("%Y-%m-%d"))[["id", "date", "sales"]]
    matched = forecasts.merge(truth, on=["id", "date"], validate="many_to_one", how="left")
    np.testing.assert_array_equal(matched.actual, matched.sales)
    expected = result["series"] * result["test_days"]
    if forecasts.duplicated(["method", "id", "date"]).any():
        raise AssertionError("Duplicated forecast observations")
    for record in result["forecast_metrics"]:
        rows = forecasts.loc[forecasts.method.eq(record["method"])]
        assert len(rows) == expected
        for key, value in point_metrics(rows.actual.to_numpy(), rows.q50.to_numpy()).items():
            assert abs(value - record[key]) < 0.00011, (record["method"], key)
        assert np.isfinite(rows[["q10", "q50", "q90"]]).all().all()
        assert (rows.q10 >= 0).all() and (rows.q10 <= rows.q50).all() and (rows.q50 <= rows.q90).all()
    series = pd.read_csv(folder / "inventory-series.csv")
    assert len(series) == result["series"] * 7 * 12
    np.testing.assert_allclose(series.initial_stock + series.received, series.served + series.ending_stock, atol=1e-7)
    np.testing.assert_allclose(series.ordered, series.received + series.ending_in_transit, atol=1e-7)
    np.testing.assert_allclose(series.demand, series.served + series.lost, atol=1e-7)
    assert not series.duplicated(["scenario", "method", "id"]).any()
    for record in result["inventory"]:
        rows = series.loc[series.scenario.eq(record["scenario"]) & series.method.eq(record["method"])]
        assert len(rows) == result["series"]
        assert abs(100 * rows.served.sum() / rows.demand.sum() - record["fill_rate_pct"]) < 1e-7
        assert abs(rows.average_stock.mean() - record["average_stock_per_series"]) < 1e-7
    daily = pd.read_csv(folder / "inventory-primary-daily.csv.gz")
    assert len(daily) == expected * 7
    for (method, item), rows in daily.groupby(["method", "id"]):
        rows = rows.sort_values("date")
        aggregate = series.loc[series.primary & series.method.eq(method) & series.id.eq(item)].iloc[0]
        stock = aggregate.initial_stock
        for day in rows.itertuples():
            stock += day.receipts
            assert abs(day.served - min(stock, day.demand)) < 1e-7
            stock -= day.served
            assert abs(stock - day.ending_stock) < 1e-7
            assert abs(day.demand - day.served - day.lost) < 1e-7
    ids = sorted(cohort.id.unique())
    matrices = {method: rows.pivot(index="id", columns="date", values="q50").loc[ids].to_numpy()
                for method, rows in forecasts.groupby("method")}
    actual = forecasts.loc[forecasts.method.eq("seasonal_naive_7")].pivot(index="id", columns="date", values="actual").loc[ids].to_numpy()
    bootstrap = bootstrap_differences(actual, matrices, series.loc[series.primary], ids)
    published = {row["method"]: row for row in result["paired_cluster_bootstrap"]}
    for record in bootstrap:
        for metric, value in record.items():
            if metric != "method":
                np.testing.assert_allclose(value, published[record["method"]][metric], atol=1e-7)
    return {"forecast_rows_recomputed": len(forecasts), "inventory_paths_checked": len(series),
            "primary_daily_movements_checked": len(daily), "paired_bootstrap_resamples_recomputed": 10000, "status": "PASS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.report), indent=2))
