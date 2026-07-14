#!/usr/bin/env python3
"""Run and freeze the exact 32-case P139 local service qualification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p139_release_evidence import (  # noqa: E402
    P139_READY_STATUS,
    assemble_p139_final_evidence,
    build_p139_freeze_manifest,
    build_p139_preliminary_evidence,
)
from app.services.p139_runner import (  # noqa: E402
    p139_release_case_catalog,
    run_p139_preliminary_matrix,
)

DEFAULT_PROFILE = ROOT / "evals/p139/input/local-triage-service-profile.json"
DEFAULT_OUTPUT = ROOT / "evals/p139/output"
DEFAULT_REVIEW = ROOT / "evals/p139/final-implementation-review.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preliminary", "final"), default="final")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--canonical-matrix", type=Path, default=DEFAULT_OUTPUT / "canonical-matrix.json")
    parser.add_argument("--freeze-manifest", type=Path, default=DEFAULT_OUTPUT / "freeze-manifest.json")
    parser.add_argument("--final-review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()
    try:
        profile = _read_json(args.profile)
        if profile.get("cases") != p139_release_case_catalog():
            raise ValueError("p139_profile_catalog_drift")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        matrix_path = args.canonical_matrix
        manifest_path = args.freeze_manifest
        evidence_path = args.output_dir / "release-evidence.json"
        if args.mode == "preliminary":
            matrix = run_p139_preliminary_matrix(ROOT)
            manifest = build_p139_freeze_manifest(
                project_root=ROOT,
                profile=profile,
                matrix=matrix,
            )
            evidence = build_p139_preliminary_evidence(matrix, manifest)
            _write_json(matrix_path, matrix)
            _write_json(manifest_path, manifest)
            _write_json(evidence_path, evidence)
        else:
            matrix_before = matrix_path.read_bytes()
            manifest_before = manifest_path.read_bytes()
            evidence = assemble_p139_final_evidence(
                _read_json(matrix_path),
                manifest=_read_json(manifest_path),
                review=_read_json(args.final_review),
                project_root=ROOT,
                profile=profile,
            )
            if matrix_path.read_bytes() != matrix_before or manifest_path.read_bytes() != manifest_before:
                raise ValueError("p139_final_mode_rewrote_frozen_input")
            _write_json(evidence_path, evidence)
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "release_status": evidence["status"],
                    "evidence_hash": evidence["evidence_hash"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        if args.mode == "final" and evidence["status"] != P139_READY_STATUS:
            return 1
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "release_status": "p139_blocked",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
