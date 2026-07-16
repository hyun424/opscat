#!/usr/bin/env python3
"""P149 qualification wrapper."""
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
from app.services.p149_canary_control import (  # noqa: E402
    P149_CONTRACT,
    assemble_p149_release_evidence,
    run_p149_qualification,
    validate_p149_final_review,
    validate_p149_freeze_manifest,
    validate_p149_report,
    validate_p149_release_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P149 preliminary or final qualification.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preliminary = subparsers.add_parser("preliminary")
    preliminary.add_argument("--predecessor", type=Path)
    preliminary.add_argument("--cases", type=Path, default=Path("evals/p149/input/canary-cases.json"))
    preliminary.add_argument("--output-dir", type=Path, required=True)
    preliminary.add_argument("--kill-switch-engaged", action="store_true")

    final = subparsers.add_parser("final")
    final.add_argument("--report", type=Path, required=True)
    final.add_argument("--freeze-manifest", type=Path, required=True)
    final.add_argument("--final-review", type=Path, required=True)
    final.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "preliminary":
        if args.predecessor is not None:
            raise SystemExit("P149 canonical qualification requires the path-backed P148 release; --predecessor is not accepted")
        cases_doc = json.loads(args.cases.read_text(encoding="utf-8"))
        cases = cases_doc.get("cases") if isinstance(cases_doc, dict) else cases_doc
        if not isinstance(cases, list):
            raise SystemExit("cases_json_must_be_list_or_object_with_cases")
        result = run_p149_qualification(
            predecessor=None,
            cases=cases,
            output_dir=args.output_dir,
            kill_switch_engaged=args.kill_switch_engaged,
            project_root=ROOT,
            evidence_mode="canonical",
            cases_path=args.cases,
        )
        print(json.dumps({"report_hash": result["report"]["report_hash"], "manifest_hash": result["freeze_manifest"]["manifest_hash"]}, sort_keys=True))
        return 0

    report = validate_p149_report(
        validate_current_release_bindings(
            ROOT,
            load_json(args.report),
            P149_CONTRACT,
            require_companion_artifacts=True,
        )
    )
    manifest = validate_p149_freeze_manifest(load_json(args.freeze_manifest))
    review = validate_p149_final_review(load_json(args.final_review), report=report, freeze_manifest=manifest)
    release = validate_p149_release_evidence(assemble_p149_release_evidence(report=report, freeze_manifest=manifest, final_review=review), report=report)
    write_release_evidence(args.output_dir, release)
    print(json.dumps({"evidence_hash": release["evidence_hash"], "status": release["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
