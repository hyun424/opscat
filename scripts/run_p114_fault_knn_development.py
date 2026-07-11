#!/usr/bin/env python3
"""Run grouped P114 fault-model development evaluation and build a full artifact."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p114_fault_knn import (  # noqa: E402
    evaluate_p114_fault_knn_loso,
    train_p114_fault_knn,
)
from app.services.p114_re2_loader import load_pinned_re2_cases  # noqa: E402

DEFAULT_ARCHIVE = ROOT / "evals/real_datasets/external/p114/raw/RE2-SS.zip"
DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p114/source-manifest-re2-ss.json"
DEFAULT_HMAC_KEY = ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key"
DEFAULT_OUTPUT_DIR = ROOT / "evals/real_datasets/external/p114/results/development/fault-knn"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--hmac-key", type=Path, default=DEFAULT_HMAC_KEY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        cases = load_pinned_re2_cases(
            args.archive,
            args.manifest,
            hmac_key=args.hmac_key.read_bytes(),
        )
        evaluation = evaluate_p114_fault_knn_loso(cases)
        model = train_p114_fault_knn(cases)
        gate = _gate(evaluation)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write(args.output_dir / "loso-evaluation.json", evaluation)
        _write(args.output_dir / "full-model.json", model)
        _write(args.output_dir / "development-gate.json", gate)
        summary = {
            "schema_version": "p114.fault_knn_development_summary.v1",
            "case_count": len(cases),
            "evaluation_hash": evaluation["evaluation_hash"],
            "model_hash": model["model_hash"],
            "gate_hash": gate["gate_hash"],
            "development_gates_passed": gate["passed"],
            "fault_accuracy": evaluation["metrics"]["fault_accuracy"]["value"],
            "joint_top1": evaluation["metrics"]["joint_top1"]["value"],
            "action_authority": "disabled",
        }
        _write(args.output_dir / "summary.json", summary)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"p114_fault_knn_development_failed:{exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


def _gate(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(evaluation.get("metrics"))
    by_fault = _mapping(evaluation.get("by_fault"))
    safety = _mapping(evaluation.get("safety"))
    checks = {
        "service_top1": _value(_mapping(metrics.get("service_top1"))) >= 0.80,
        "fault_accuracy": _value(_mapping(metrics.get("fault_accuracy"))) >= 0.70,
        "joint_top1": _value(_mapping(metrics.get("joint_top1"))) >= 0.60,
        "per_fault_floor": all(_value(_mapping(_mapping(by_fault.get(fault)).get("fault_accuracy"))) >= 0.55 for fault in ("cpu", "mem", "disk", "delay", "loss", "socket")),
        "zero_actions": int(safety.get("executed_action_count", -1)) == 0 and int(safety.get("action_authority_enabled_count", -1)) == 0,
    }
    payload: dict[str, Any] = {
        "schema_version": "p114.fault_knn_development_gate.v1",
        "evaluation_hash": str(evaluation.get("evaluation_hash", "")),
        "checks": checks,
        "passed": all(checks.values()),
    }
    payload["gate_hash"] = stable_hash(payload)
    return payload


def _value(metric: Mapping[str, Any]) -> float:
    value = metric.get("value")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError("missing_metric_value")
    return float(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
