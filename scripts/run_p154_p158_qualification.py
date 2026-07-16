#!/usr/bin/env python3
"""Run one ordered P154-P158 qualification phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p147_p152_contracts import write_canonical_json  # noqa: E402
from app.services.p154_p158_operator_replacement import (  # noqa: E402
    SPECS,
    assemble_release_evidence,
    build_freeze_manifest,
    evaluate_p154,
    evaluate_p155,
    evaluate_p156,
    evaluate_p157,
    evaluate_p158,
    load_phase_input,
    validate_final_review,
    validate_freeze_manifest,
    validate_release_evidence,
    validate_report,
)

EVALUATORS = {
    "p154": evaluate_p154,
    "p155": evaluate_p155,
    "p156": evaluate_p156,
    "p157": evaluate_p157,
    "p158": evaluate_p158,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=tuple(EVALUATORS))
    parser.add_argument("--mode", choices=("preliminary", "final", "validate"), default="preliminary")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    phase = args.phase
    output_dir = args.output_dir or Path(f"evals/{phase}/output")
    try:
        if args.mode == "validate":
            release = load_phase_input(output_dir / "release-evidence.json", f"{phase}-release")
            validated = validate_release_evidence(phase, release, project_root=ROOT)
            print(json.dumps({"phase": phase, "status": validated["status"], "evidence_hash": validated["evidence_hash"]}, sort_keys=True))
            return 0
        input_path = args.input or Path(f"evals/{phase}/input/cases.json")
        payload = load_phase_input(input_path, phase)
        spec = SPECS[phase]
        predecessor = load_phase_input(ROOT / spec.predecessor_path, f"{spec.predecessor_phase}-release")
        report = EVALUATORS[phase](payload, predecessor, project_root=ROOT)
        freeze = build_freeze_manifest(phase, report, project_root=ROOT)
        write_canonical_json(output_dir / "report.json", report)
        write_canonical_json(output_dir / "freeze-manifest.json", freeze)
        if args.mode == "preliminary":
            print(json.dumps({"phase": phase, "mode": "preliminary", "report_hash": report["report_hash"]}, sort_keys=True))
            return 0
        if args.review is None:
            raise SystemExit("final mode requires --review")
        canonical_report = validate_report(phase, load_phase_input(output_dir / "report.json", f"{phase}-report"))
        canonical_freeze = validate_freeze_manifest(phase, load_phase_input(output_dir / "freeze-manifest.json", f"{phase}-freeze"))
        review = validate_final_review(
            phase,
            load_phase_input(args.review, f"{phase}-review"),
            report=canonical_report,
            freeze=canonical_freeze,
        )
        release = assemble_release_evidence(phase, canonical_report, canonical_freeze, review)
        write_canonical_json(output_dir / "release-evidence.json", release)
        validate_release_evidence(phase, release, project_root=ROOT)
        print(json.dumps({"phase": phase, "mode": "final", "status": release["status"], "evidence_hash": release["evidence_hash"]}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"phase": phase, "status": "blocked", "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
