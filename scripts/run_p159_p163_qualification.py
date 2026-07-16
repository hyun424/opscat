#!/usr/bin/env python3
"""Run one ordered P159-P163 qualification phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_judgment import NvidiaLLMJudgmentProvider, run_llm_judgment_from_packet  # noqa: E402
from app.services.p147_p152_contracts import write_canonical_json  # noqa: E402
from app.services.p159_p163_live_operator_program import (  # noqa: E402
    SPECS,
    assemble_release_evidence,
    build_freeze_manifest,
    evaluate_p159,
    evaluate_p160,
    evaluate_p161,
    evaluate_p162,
    evaluate_p163,
    load_phase_input,
    validate_final_review,
    validate_freeze_manifest,
    validate_release_evidence,
    validate_report,
)

EVALUATORS = {
    "p159": evaluate_p159,
    "p160": evaluate_p160,
    "p161": evaluate_p161,
    "p162": evaluate_p162,
    "p163": evaluate_p163,
}


def _run_nvidia_live(input_path: Path, output_path: Path) -> None:
    payload = load_phase_input(input_path, "p161")
    provider = NvidiaLLMJudgmentProvider()
    results = []
    for case in payload["cases"]:
        evidence = [{"id": item["id"], "summary": item["signal"], "risk_flags": []} for item in case["evidence"]]
        packet = {
            "incident": {"id": case["case_id"], "summary": "blind incident diagnosis"},
            "evidence": evidence,
            "candidate_hypotheses": [{"label": label, "confidence": 0.5, "evidence_citations": [item["id"] for item in case["evidence"]]} for label in case["deterministic"]["labels"]],
            "candidate_runbooks": [],
            "required_output_schema": {
                "hypotheses": "array",
                "recommended_route": "approval_required|human_required|blocked",
                "safe_actions": "array",
                "forbidden_actions_detected": "array",
                "missing_evidence": "array",
                "verification_plan": "array",
                "evidence_citations": "array",
                "boundary": "object"
            }
        }
        result = run_llm_judgment_from_packet(packet, provider=provider).to_dict()
        results.append(
            {
                "case_id": case["case_id"],
                "truth": case["truth"],
                "validation": result["validation"],
                "citation_check": result["citation_check"],
                "safety_gate": result["safety_gate"],
                "judgment": result["judgment"],
            }
        )
    write_canonical_json(
        output_path,
        {
            "schema_version": "p161.nvidia_live_experiment.v1",
            "release_evidence_eligible": False,
            "provider": "nvidia",
            "case_count": len(results),
            "results": results,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=tuple(EVALUATORS))
    parser.add_argument("--mode", choices=("preliminary", "final", "validate", "nvidia-live"), default="preliminary")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--live-output", type=Path, default=Path("evals/p161/live-nvidia-experiment.json"))
    args = parser.parse_args(argv)
    phase = args.phase
    output_dir = args.output_dir or Path(f"evals/{phase}/output")
    try:
        if args.mode == "nvidia-live":
            if phase != "p161":
                raise ValueError("nvidia-live mode is only valid for p161")
            _run_nvidia_live(args.input or Path("evals/p161/input/cases.json"), args.live_output)
            print(json.dumps({"phase": phase, "mode": "nvidia-live", "release_evidence_eligible": False}, sort_keys=True))
            return 0
        if args.mode == "validate":
            release = load_phase_input(output_dir / "release-evidence.json", f"{phase}-release")
            validated = validate_release_evidence(phase, release, project_root=ROOT)
            print(json.dumps({"phase": phase, "status": validated["status"], "evidence_hash": validated["evidence_hash"]}, sort_keys=True))
            return 0
        payload = load_phase_input(args.input or Path(f"evals/{phase}/input/cases.json"), phase)
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
            raise ValueError("final mode requires --review")
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
