from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from research.data import prepare_m5, prepare_uci_online_retail
from research.experiment import run_experiment
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
    train = subparsers.add_parser("train", help="Compare demand-aware baselines, LSTM, GRU and Transformer")
    train.add_argument("--data", type=Path, default=Path("data/processed/uci-online-retail/uci_online_retail_subset.csv.gz"))
    train.add_argument("--manifest", type=Path, default=Path("data/processed/uci-online-retail/manifest.json"))
    train.add_argument("--output", type=Path, default=Path("storage/app/experiments"))
    train.add_argument("--models", nargs="+", choices=["lstm", "gru", "transformer"], default=["lstm", "gru", "transformer"])
    train.add_argument("--epochs", type=int, default=100)
    train.add_argument("--patience", type=int, default=10)
    train.add_argument("--batch-size", type=int, default=64)
    train.add_argument("--folds", type=int, choices=range(1, 7), default=3)
    args = parser.parse_args()

    if args.action == "prepare-m5":
        print(json.dumps(asdict(prepare_m5(args.raw_dir, args.output_dir, args.series, args.seed)), ensure_ascii=False))
    elif args.action == "prepare-uci":
        print(json.dumps(asdict(prepare_uci_online_retail(args.source, args.output_dir, args.series, args.seed)), ensure_ascii=False))
    elif args.action == "train":
        config = TrainingConfig(max_epochs=args.epochs, patience=args.patience, batch_size=args.batch_size)
        result = run_experiment(args.data, args.manifest, args.output, args.models, config, folds=args.folds)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
