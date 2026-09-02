#!/usr/bin/env python
"""JSON command-line interface for the robust demand baseline."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from typing import Any, Mapping, Sequence

if __package__:
    from .forecasting import build_report_document, forecast_product, load_inventory_data
    from .runtime_model import resolve_runtime_model
else:
    from forecasting import build_report_document, forecast_product, load_inventory_data
    from runtime_model import resolve_runtime_model


class CliInputError(ValueError):
    """An input error that must be returned as JSON."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliInputError(message)


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _decode_payload(payload: str | None, payload_b64: str | None) -> dict[str, Any]:
    if payload is not None and payload_b64 is not None:
        raise CliInputError("Use either --payload or --payload-b64, not both.")
    raw = payload
    if payload_b64 is not None:
        try:
            raw = base64.b64decode(payload_b64.strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise CliInputError("Malformed base64 payload.") from exc
    if raw is None:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliInputError(f"Malformed JSON payload: {exc.msg}.") from exc
    if not isinstance(decoded, dict):
        raise CliInputError("Payload must be a JSON object.")
    return decoded


def _normalize_formats(value: Any) -> list[str]:
    if value is None:
        return ["pdf"]
    if isinstance(value, str):
        formats = [item.strip().lower() for item in value.split(",") if item.strip()]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        formats = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        raise CliInputError("formats must be an array or a comma-separated string.")
    formats = list(dict.fromkeys(formats))
    if not formats or any(item not in {"pdf", "pptx"} for item in formats):
        raise CliInputError("formats may contain only pdf and pptx.")
    return formats


def run_simulate(product_id: Any, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        normalized_id = int(product_id)
    except (TypeError, ValueError) as exc:
        raise CliInputError("product_id must be an integer.") from exc
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, Mapping):
        raise CliInputError("overrides must be a JSON object.")

    data = load_inventory_data()
    if normalized_id not in set(data["products"]["id"].astype(int)):
        raise CliInputError(f"Unknown product_id: {normalized_id}")
    forecast = forecast_product(normalized_id, data, overrides=overrides, strategy="standard")
    runtime_model, registry_warning = resolve_runtime_model()
    return {
        "product_id": normalized_id,
        "product_name": forecast["product_name"],
        "dates": forecast["dates"],
        "demand": forecast["demand"],
        "q10": forecast["q10"],
        "q90": forecast["q90"],
        "stock": forecast["stock"],
        "safety_stock": forecast["safety_stock"],
        "data_as_of": forecast["data_as_of"],
        "model": runtime_model,
        "quality": forecast["quality"],
        "warnings": list(dict.fromkeys([*forecast["warnings"], *([registry_warning] if registry_warning else [])])),
    }


def run_report(report_type: Any, formats: Any) -> dict[str, Any]:
    if not isinstance(report_type, str) or not report_type.strip():
        raise CliInputError("type must be a non-empty string.")
    normalized_formats = _normalize_formats(formats)
    if __package__:
        from .report_generator import generate_report_bundle
    else:
        from report_generator import generate_report_bundle

    bundle = generate_report_bundle(report_type.strip().lower(), normalized_formats)
    runtime_model, registry_warning = resolve_runtime_model()
    bundle["metadata"]["model"] = runtime_model
    public_artifacts = [
        {"format": artifact["format"], "filename": artifact["filename"]}
        for artifact in bundle["artifacts"]
    ]
    pdf = next((artifact for artifact in public_artifacts if artifact["format"] == "pdf"), None)
    presentation = next((artifact for artifact in public_artifacts if artifact["format"] == "pptx"), None)
    return {
        "success": True,
        "report_id": bundle["report_id"],
        "filename": pdf["filename"] if pdf else None,
        "presentation_filename": presentation["filename"] if presentation else None,
        "artifacts": public_artifacts,
        "metadata": bundle["metadata"],
        "warnings": list(dict.fromkeys([*bundle["warnings"], *([registry_warning] if registry_warning else [])])),
    }


def run_planning() -> dict[str, Any]:
    document = build_report_document("standard")
    runtime_model, registry_warning = resolve_runtime_model()
    actions = []
    for item in document["product_actions"]:
        actions.append({key: value for key, value in item.items() if key != "forecast"})
    return {
        "success": True,
        "data_as_of": document["metadata"]["data_as_of"],
        "model": runtime_model,
        "portfolio": document["portfolio"],
        "quality": document["quality"],
        "evaluation": document["metrics"],
        "warnings": list(dict.fromkeys([*document["warnings"], *([registry_warning] if registry_warning else [])])),
        "actions": actions,
    }


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description="Ray OS robust forecasting engine")
    parser.add_argument("action", choices=("simulate", "report", "planning"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--payload")
    group.add_argument("--payload-b64")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output()
    try:
        args = _parser().parse_args(argv)
        payload = _decode_payload(args.payload, args.payload_b64)
        if args.action == "simulate":
            result = run_simulate(payload.get("product_id", 1), payload.get("overrides", {}))
        elif args.action == "report":
            result = run_report(payload.get("type", "standard"), payload.get("formats"))
        else:
            result = run_planning()
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:
        error = {"success": False, "error": str(exc) or exc.__class__.__name__}
        print(json.dumps(error, ensure_ascii=False, allow_nan=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
