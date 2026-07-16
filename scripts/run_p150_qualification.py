#!/usr/bin/env python3
"""P150 qualification and wall-clock runner wrapper."""
# ruff: noqa: E402,I001

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p147_p152_contracts import load_json, validate_current_release_bindings, write_release_evidence  # noqa: E402
from app.services.p150_unattended_soak import (  # noqa: E402
    P150_CONTRACT,
    assemble_p150_release_evidence_from_paths,
    run_p150_qualification,
    run_canonical_wall_clock_runner,
    validate_p150_final_review,
    validate_p150_freeze_manifest,
    validate_p150_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P150 preliminary, final, or wall-clock qualification.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preliminary = subparsers.add_parser("preliminary")
    preliminary.add_argument("--predecessor", type=Path)
    preliminary.add_argument("--fast-schedule", type=Path, default=Path("evals/p150/input/fast-schedule.json"))
    preliminary.add_argument("--wall-clock-result", type=Path, required=True)
    preliminary.add_argument("--wall-clock-ledger", type=Path, required=True)
    preliminary.add_argument("--wall-clock-checkpoint", type=Path, required=True)
    preliminary.add_argument("--output-dir", type=Path, required=True)

    final = subparsers.add_parser("final")
    final.add_argument("--report", type=Path, required=True)
    final.add_argument("--freeze-manifest", type=Path, required=True)
    final.add_argument("--final-review", type=Path, required=True)
    final.add_argument("--wall-clock-result", type=Path, required=True)
    final.add_argument("--wall-clock-ledger", type=Path, required=True)
    final.add_argument("--wall-clock-checkpoint", type=Path, required=True)
    final.add_argument("--output-dir", type=Path, required=True)

    wall_clock = subparsers.add_parser("wall-clock")
    wall_clock.add_argument("--output-dir", type=Path, required=True)
    wall_clock.add_argument("--no-resume", action="store_true")

    args = parser.parse_args()
    if args.command == "wall-clock":
        receipt = run_canonical_wall_clock_runner(output_dir=args.output_dir, resume=not args.no_resume)
        print(json.dumps({"receipt_hash": receipt["receipt_hash"], "wall_clock_qualified": receipt["wall_clock_qualified"]}, sort_keys=True))
        return 0
    if args.command == "preliminary":
        result = run_p150_qualification(
            predecessor_path=args.predecessor,
            fast_schedule=load_json(args.fast_schedule),
            wall_clock_result=load_json(args.wall_clock_result),
            wall_clock_result_path=args.wall_clock_result,
            wall_clock_ledger_path=args.wall_clock_ledger,
            wall_clock_checkpoint_path=args.wall_clock_checkpoint,
            output_dir=args.output_dir,
            project_root=ROOT,
            evidence_mode="canonical",
        )
        print(json.dumps({"report_hash": result["report"]["report_hash"], "manifest_hash": result["freeze_manifest"]["manifest_hash"]}, sort_keys=True))
        return 0

    report = validate_p150_report(load_json(args.report))
    validate_current_release_bindings(
        ROOT,
        report,
        P150_CONTRACT,
        require_companion_artifacts=True,
    )
    manifest = validate_p150_freeze_manifest(load_json(args.freeze_manifest))
    review = validate_p150_final_review(load_json(args.final_review), report=report, freeze_manifest=manifest)
    release = assemble_p150_release_evidence_from_paths(
        report=report,
        freeze_manifest=manifest,
        final_review=review,
        wall_clock_result_path=args.wall_clock_result,
        wall_clock_ledger_path=args.wall_clock_ledger,
        wall_clock_checkpoint_path=args.wall_clock_checkpoint,
    )
    write_release_evidence(args.output_dir, release)
    print(json.dumps({"evidence_hash": release["evidence_hash"], "status": release["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
