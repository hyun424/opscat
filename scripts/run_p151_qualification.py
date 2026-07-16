#!/usr/bin/env python3
"""Run P151 qualification or create its pre-existing prediction commit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import load_json, validate_current_release_bindings, write_canonical_json
from app.services.p151_ground_truth_quality import (
    P151_CONTRACT,
    assemble_p151_release_evidence,
    build_p151_freeze_manifest,
    build_p151_nvidia_non_release_report,
    commit_prediction_packet,
    file_sha256,
    predecessor_from_default_path,
    run_p151_qualification,
    validate_prediction_commit,
)

DEFAULT_CORPUS_PATH = Path("evals/p151/input/sealed-corpus.json")
DEFAULT_PREDICTION_PACKET_PATH = Path("evals/p151/input/prediction-packet.json")
DEFAULT_PREDICTION_COMMIT_PATH = Path("evals/p151/input/prediction-commit.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("commit", "preliminary", "final", "nvidia-non-release"), default="preliminary")
    parser.add_argument("--rows", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--prediction-packet", type=Path, default=DEFAULT_PREDICTION_PACKET_PATH)
    parser.add_argument("--prediction-commit", type=Path, default=DEFAULT_PREDICTION_COMMIT_PATH)
    parser.add_argument("--truth-seal-hash")
    parser.add_argument("--predecessor", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--nvidia-results", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("evals/p151/output"))
    args = parser.parse_args()

    packet = load_json(args.prediction_packet)
    packet_raw_hash = file_sha256(args.prediction_packet)

    if args.mode == "commit":
        if args.truth_seal_hash is None:
            raise SystemExit("commit mode requires --truth-seal-hash; it will not open the truth corpus")
        commit = commit_prediction_packet(
            packet,
            truth_seal_hash=args.truth_seal_hash,
            prediction_packet_raw_file_hash=packet_raw_hash,
        )
        write_canonical_json(args.prediction_commit, commit)
        print(json.dumps({"phase": "p151", "mode": "commit", "commit_hash": commit["commit_hash"]}, sort_keys=True))
        return 0

    commit = load_json(args.prediction_commit)
    commit_raw_hash = file_sha256(args.prediction_commit)
    validate_prediction_commit(
        commit,
        prediction_packet=packet,
        prediction_packet_raw_file_hash=packet_raw_hash,
    )

    rows = _rows(args.rows)
    predecessor = load_json(args.predecessor) if args.predecessor else predecessor_from_default_path(Path.cwd())
    report = run_p151_qualification(
        rows=rows,
        prediction_packet=packet,
        prediction_commit=commit,
        prediction_packet_raw_file_hash=packet_raw_hash,
        prediction_commit_raw_file_hash=commit_raw_hash,
        predecessor=predecessor,
        output_dir=None,
        project_root=Path.cwd(),
        evidence_mode="canonical",
        truth_path=args.rows,
        prediction_packet_path=args.prediction_packet,
        prediction_commit_path=args.prediction_commit,
    )
    freeze = build_p151_freeze_manifest(project_root=Path.cwd(), report=report)
    write_canonical_json(args.output_dir / "report.json", report)
    write_canonical_json(args.output_dir / "freeze-manifest.json", freeze)
    if args.mode == "nvidia-non-release":
        nvidia_results = load_json(args.nvidia_results) if args.nvidia_results else {}
        nvidia_report = build_p151_nvidia_non_release_report(canonical_report=report, nvidia_results=nvidia_results)
        write_canonical_json(args.output_dir / "nvidia-non-release-report.json", nvidia_report)
    elif args.mode == "final":
        if args.review is None:
            raise SystemExit("final mode requires --review; runner will not fabricate manual review")
        validate_current_release_bindings(
            Path.cwd(),
            report,
            P151_CONTRACT,
            require_companion_artifacts=True,
        )
        review = load_json(args.review)
        release = assemble_p151_release_evidence(report=report, freeze=freeze, review=review)
        write_canonical_json(args.output_dir / "release-evidence.json", release)
    print(json.dumps({"phase": "p151", "mode": args.mode, "status": report["status"], "report_hash": report["report_hash"]}, sort_keys=True))
    return 0


def _rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise SystemExit("rows file must contain a JSON list")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
