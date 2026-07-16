#!/usr/bin/env python3
"""Run P152 preliminary or final readiness artifact assembly."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import (
    load_json,
    predecessor_from_path,
    validate_current_release_bindings,
    write_canonical_json,
)
from app.services.p152_operator_readiness import P152_CONTRACT, assemble_p152_release_evidence, build_p152_freeze_manifest, run_p152_qualification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preliminary", "final"), default="preliminary")
    parser.add_argument("--predecessors", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("evals/p152/output"))
    args = parser.parse_args()

    if args.predecessors is not None:
        raise SystemExit("P152 canonical qualification requires path-backed P146-P151 predecessors; --predecessors is not accepted")
    predecessors = _predecessors()
    cases = _load_list(args.cases) if args.cases else _load_list(Path("evals/p152/input/integration-cases.json"))
    report = run_p152_qualification(
        predecessors=predecessors,
        integration_cases=cases,
        output_dir=None,
        project_root=Path.cwd(),
        evidence_mode="canonical",
    )
    freeze = build_p152_freeze_manifest(project_root=Path.cwd(), report=report)
    write_canonical_json(args.output_dir / "report.json", report)
    write_canonical_json(args.output_dir / "freeze-manifest.json", freeze)
    if args.mode == "final":
        if args.review is None:
            raise SystemExit("final mode requires --review; runner will not fabricate manual review")
        validate_current_release_bindings(
            Path.cwd(),
            report,
            P152_CONTRACT,
            require_companion_artifacts=True,
        )
        review = load_json(args.review)
        release = assemble_p152_release_evidence(report=report, freeze=freeze, review=review)
        write_canonical_json(args.output_dir / "release-evidence.json", release)
    print(json.dumps({"phase": "p152", "mode": args.mode, "status": report["status"], "report_hash": report["report_hash"]}, sort_keys=True))
    return 0


def _load_list(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise SystemExit(f"{path} must contain a JSON list")
    return value


def _predecessors() -> list[dict[str, Any]]:
    return [predecessor_from_path(Path.cwd(), spec) for spec in P152_CONTRACT.predecessors]


if __name__ == "__main__":
    raise SystemExit(main())
