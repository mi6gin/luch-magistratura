from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from research.data import prepare_excel_inventory, prepare_local_inventory, prepare_m5, prepare_uci_online_retail
from research.analysis import analyze_dataset
from research.experiment import run_experiment
from research.tuning import tune_models
from research.scenarios import benchmark_scenarios
from research.scalability import benchmark_scalability
from research.reporting import build_research_report
from research.trainer import TrainingConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Rayventory research dataset pipeline")
    subparsers = parser.add_subparsers(dest="action", required=True)
    prepare = subparsers.add_parser("prepare-m5", help="Build a deterministic research subset from official M5 files")
    prepare.add_argument("--raw-dir", type=Path, default=Path("data/raw/m5"))
    prepare.add_argument("--output-dir", type=Path, default=Path("data/processed/m5"))
    prepare.add_argument("--series", type=int, default=300)
    prepare.add_argument("--seed", type=int, default=42)
    prepare_uci = subparsers.add_parser("prepare-uci", help="Prepare UCI Online Retail II without an account")
    prepare_uci.add_argument("--source", type=Path, default=Path("data/raw/uci-online-retail/online_retail_II.xlsx"))
    prepare_uci.add_argument("--output-dir", type=Path, default=Path("data/processed/uci-online-retail"))
    prepare_uci.add_argument("--series", type=int, default=300)
    prepare_uci.add_argument("--seed", type=int, default=42)
    prepare_local = subparsers.add_parser("prepare-local", help="Prepare private training data from the local SQLite database")
    prepare_local.add_argument("--database", type=Path, default=Path("storage/app/rayventory/inventory_forecast.db"))
    prepare_local.add_argument("--output-dir", type=Path, default=Path("data/processed/local-inventory"))
    prepare_local.add_argument("--series", type=int, default=1000)
    prepare_local.add_argument("--seed", type=int, default=42)
    prepare_local.add_argument("--branch-id", type=int, default=1)
    prepare_excel = subparsers.add_parser("prepare-excel", help="Prepare research data directly from a Rayventory Excel workbook")
    prepare_excel.add_argument("--source", type=Path, required=True)
    prepare_excel.add_argument("--output-dir", type=Path, default=Path("data/processed/excel-inventory"))
    prepare_excel.add_argument("--series", type=int, default=1000)
    prepare_excel.add_argument("--seed", type=int, default=42)
    analyze = subparsers.add_parser("analyze", help="Profile demand, quality, seasonality and external factors")
    analyze.add_argument("--data", type=Path, required=True)
    analyze.add_argument("--manifest", type=Path, required=True)
    analyze.add_argument("--output", type=Path, default=Path("storage/app/dataset-analysis/latest.json"))
    tune = subparsers.add_parser("tune", help="Run reproducible hyperparameter search for neural architectures")
    tune.add_argument("--data", type=Path, default=Path("data/processed/uci-online-retail/uci_online_retail_subset.csv.gz"))
    tune.add_argument("--manifest", type=Path, default=Path("data/processed/uci-online-retail/manifest.json"))
    tune.add_argument("--experiments-output", type=Path, default=Path("storage/app/experiments"))
    tune.add_argument("--output", type=Path, default=Path("storage/app/tuning"))
    tune.add_argument("--models", nargs="+", choices=["lstm", "gru", "transformer"], default=["lstm", "gru", "transformer"])
    tune.add_argument("--preset", choices=["smoke", "full"], default="smoke")
    tune.add_argument("--folds", type=int, choices=range(1, 7), default=1)
    tune.add_argument("--epochs", type=int, default=3)
    tune.add_argument("--patience", type=int, default=2)
    tune.add_argument("--batch-size", type=int, default=256)
    scenarios = subparsers.add_parser("scenarios", help="Compare models under controlled seasonality, trend, promotion and external factors")
    scenarios.add_argument("--output", type=Path, default=Path("storage/app/scenarios"))
    scenarios.add_argument("--experiments-output", type=Path, default=Path("storage/app/experiments"))
    scenarios.add_argument("--models", nargs="+", choices=["lstm", "gru", "transformer"], default=["lstm", "gru", "transformer"])
    scenarios.add_argument("--folds", type=int, choices=range(1, 7), default=1)
    scenarios.add_argument("--epochs", type=int, default=3)
    scenarios.add_argument("--patience", type=int, default=2)
    scenarios.add_argument("--batch-size", type=int, default=256)
    scenarios.add_argument("--series", type=int, default=12)
    scenarios.add_argument("--days", type=int, default=360)
    train = subparsers.add_parser("train", help="Compare demand-aware baselines, LSTM, GRU and Transformer")
    train.add_argument("--data", type=Path, default=Path("data/processed/uci-online-retail/uci_online_retail_subset.csv.gz"))
    train.add_argument("--manifest", type=Path, default=Path("data/processed/uci-online-retail/manifest.json"))
    train.add_argument("--output", type=Path, default=Path("storage/app/experiments"))
    train.add_argument("--models", nargs="*", choices=["lstm", "gru", "transformer"], default=["lstm", "gru", "transformer"])
    train.add_argument("--epochs", type=int, default=100)
    train.add_argument("--patience", type=int, default=10)
    train.add_argument("--batch-size", type=int, default=64)
    train.add_argument("--folds", type=int, choices=range(1, 7), default=3)
    train.add_argument("--summary", action="store_true", help="Print a compact result instead of the full experiment document")
    scale = subparsers.add_parser("scale", help="Measure neural accuracy and runtime as the number of series grows")
    scale.add_argument("--data", type=Path, required=True)
    scale.add_argument("--manifest", type=Path, required=True)
    scale.add_argument("--output", type=Path, default=Path("storage/app/scalability"))
    scale.add_argument("--experiments-output", type=Path, default=Path("storage/app/experiments"))
    scale.add_argument("--models", nargs="+", choices=["lstm", "gru", "transformer"], default=["lstm", "gru", "transformer"])
    scale.add_argument("--sizes", nargs="+", type=int, default=[10, 100, 300])
    scale.add_argument("--epochs", type=int, default=3)
    scale.add_argument("--patience", type=int, default=2)
    scale.add_argument("--batch-size", type=int, default=256)
    report = subparsers.add_parser("report", help="Build the final IUP research summary and forecast charts")
    report.add_argument("--experiment", type=Path, required=True)
    report.add_argument("--scenarios", type=Path, required=True)
    report.add_argument("--scalability", type=Path, required=True)
    report.add_argument("--output", type=Path, default=Path("storage/app/research-report/latest"))
    args = parser.parse_args()

    if args.action == "prepare-m5":
        print(json.dumps(asdict(prepare_m5(args.raw_dir, args.output_dir, args.series, args.seed)), ensure_ascii=False))
    elif args.action == "prepare-uci":
        print(json.dumps(asdict(prepare_uci_online_retail(args.source, args.output_dir, args.series, args.seed)), ensure_ascii=False))
    elif args.action == "prepare-local":
        print(json.dumps(asdict(prepare_local_inventory(args.database, args.output_dir, args.series, args.seed, args.branch_id)), ensure_ascii=False))
    elif args.action == "prepare-excel":
        print(json.dumps(asdict(prepare_excel_inventory(args.source, args.output_dir, args.series, args.seed)), ensure_ascii=False))
    elif args.action == "analyze":
        print(json.dumps({"success": True, **analyze_dataset(args.data, args.manifest, args.output)}, ensure_ascii=False))
    elif args.action == "tune":
        result = tune_models(
            args.data, args.manifest, args.experiments_output, args.output, args.models,
            args.preset, args.folds, args.epochs, args.patience, args.batch_size,
        )
        print(json.dumps({
            "success": True,
            "tuning_id": result["tuning_id"],
            "winner": result["winner"]["model"],
            "winner_wape_pct": result["winner"]["metrics"]["wape_pct"],
            "trials": len(result["trials"]),
        }, ensure_ascii=False))
    elif args.action == "scenarios":
        config = TrainingConfig(max_epochs=args.epochs, patience=args.patience, batch_size=args.batch_size)
        result = benchmark_scenarios(
            args.output, args.experiments_output, args.models, config,
            args.folds, args.series, args.days,
        )
        print(json.dumps({
            "success": True, "benchmark_id": result["benchmark_id"],
            "scenarios": {item["scenario"]: item["winner"] for item in result["scenarios"]},
            "total_seconds": result["total_seconds"],
        }, ensure_ascii=False))
    elif args.action == "train":
        config = TrainingConfig(max_epochs=args.epochs, patience=args.patience, batch_size=args.batch_size)
        result = run_experiment(args.data, args.manifest, args.output, args.models, config, folds=args.folds)
        output = {
            "success": True,
            "experiment_id": result["experiment_id"],
            "champion": result["champion"],
            "ranking": result["ranking"],
        } if args.summary else result
        print(json.dumps(output, ensure_ascii=False))
    elif args.action == "scale":
        config = TrainingConfig(max_epochs=args.epochs, patience=args.patience, batch_size=args.batch_size)
        result = benchmark_scalability(
            args.data, args.manifest, args.output, args.experiments_output,
            args.models, args.sizes, config,
        )
        print(json.dumps({"success": True, "benchmark_id": result["benchmark_id"], "results": result["results"]}, ensure_ascii=False))
    elif args.action == "report":
        result = build_research_report(args.experiment, args.scenarios, args.scalability, args.output)
        print(json.dumps({
            "success": True, "overall_winner": result["overall_winner"],
            "best_neural": result["best_neural"], "output": str(args.output),
        }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exception:
        print(json.dumps({"success": False, "error": str(exception)}, ensure_ascii=False))
        raise SystemExit(1) from None
