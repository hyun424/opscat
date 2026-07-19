#!/usr/bin/env python3
"""Run P176 qualification assembly from explicit observed result artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p176_release import (  # noqa: E402
    assemble_release_evidence,
    build_readiness_artifact,
    build_release_artifacts,
    load_json,
    validate_release_evidence,
    write_canonical_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("readiness", "preliminary", "final", "validate"), default="preliminary")
    parser.add_argument("--outcomes", type=Path)
    parser.add_argument("--healthy-results", type=Path)
    parser.add_argument("--safety-counters", type=Path)
    parser.add_argument("--agent-ledger", type=Path)
    parser.add_argument("--evaluator-ledger", type=Path)
    parser.add_argument("--release-inputs-manifest", type=Path)
    parser.add_argument("--live-artifact-manifest", type=Path)
    parser.add_argument("--billing-report", type=Path)
    parser.add_argument("--teardown-proof", type=Path)
    parser.add_argument("--terminal-stop-at")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals/p176/output")
    args = parser.parse_args(argv)

    try:
        if args.mode == "validate":
            release = load_json(args.output_dir / "release-evidence.json")
            validated = validate_release_evidence(_mapping(release, "release"), project_root=ROOT)
            print(json.dumps({"phase": "p176", "status": validated["status"], "evidence_hash": validated["evidence_hash"]}, sort_keys=True))
            return 0

        supplied = [args.outcomes, args.healthy_results, args.safety_counters, args.agent_ledger, args.evaluator_ledger]
        if args.mode == "readiness" or all(item is None for item in supplied):
            readiness = build_readiness_artifact(project_root=ROOT)
            write_canonical_json(args.output_dir / "readiness-not-executed.json", readiness)
            print(json.dumps({"phase": "p176", "mode": "readiness", "status": readiness["status"], "qualified": False}, sort_keys=True))
            return 0
        if any(item is None for item in supplied):
            raise ValueError("preliminary/final modes require --outcomes --healthy-results --safety-counters --agent-ledger --evaluator-ledger")
        live_supplied = [
            args.release_inputs_manifest,
            args.live_artifact_manifest,
            args.billing_report,
            args.teardown_proof,
            args.terminal_stop_at,
        ]
        if any(item is not None for item in live_supplied) and any(item is None for item in live_supplied):
            raise ValueError(
                "live evidence args require all or none: --release-inputs-manifest --live-artifact-manifest "
                "--billing-report --teardown-proof --terminal-stop-at"
            )

        artifacts = build_release_artifacts(
            project_root=ROOT,
            outcomes=_sequence(load_json(args.outcomes), "outcomes"),
            healthy_results=_sequence(load_json(args.healthy_results), "healthy_results"),
            safety_counters=_mapping(load_json(args.safety_counters), "safety_counters"),
            agent_visible_ledger=_sequence(load_json(args.agent_ledger), "agent_ledger"),
            evaluator_only_ledger=_sequence(load_json(args.evaluator_ledger), "evaluator_ledger"),
            release_inputs_manifest=(
                _mapping(load_json(args.release_inputs_manifest), "release_inputs_manifest")
                if args.release_inputs_manifest is not None
                else None
            ),
            live_artifact_manifest=(
                _mapping(load_json(args.live_artifact_manifest), "live_artifact_manifest")
                if args.live_artifact_manifest is not None
                else None
            ),
            billing_report=_mapping(load_json(args.billing_report), "billing_report") if args.billing_report is not None else None,
            teardown_proof=_mapping(load_json(args.teardown_proof), "teardown_proof") if args.teardown_proof is not None else None,
            terminal_stop_at=args.terminal_stop_at,
        )
        write_canonical_json(args.output_dir / "report.json", artifacts["report"])
        write_canonical_json(args.output_dir / "denominator-report.json", artifacts["denominator_report"])
        write_canonical_json(args.output_dir / "representativeness-report.json", artifacts["representativeness_report"])
        write_canonical_json(args.output_dir / "freeze-manifest.json", artifacts["freeze_manifest"])
        if args.mode == "preliminary":
            print(json.dumps({"phase": "p176", "mode": "preliminary", "report_hash": artifacts["report"]["report_hash"]}, sort_keys=True))
            return 0

        if args.review is None:
            raise ValueError("final mode requires --review")
        release = assemble_release_evidence(
            project_root=ROOT,
            report=artifacts["report"],
            denominator_report=artifacts["denominator_report"],
            representativeness_report=artifacts["representativeness_report"],
            freeze_manifest=artifacts["freeze_manifest"],
            final_review=_mapping(load_json(args.review), "review"),
        )
        write_canonical_json(args.output_dir / "release-evidence.json", release)
        print(json.dumps({"phase": "p176", "mode": "final", "status": release["status"], "evidence_hash": release["evidence_hash"]}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"phase": "p176", "status": "blocked", "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


def _sequence(value: Any, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping) and field in value:
        value = value[field]
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{field}_must_be_json_array")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field}_must_be_json_object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
