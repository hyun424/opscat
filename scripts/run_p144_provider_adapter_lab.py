from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.services.p144_release_evidence import (
    P144_BLOCKED_STATUS,
    P144_READY_STATUS,
    assemble_p144_final_evidence,
    build_p144_freeze_manifest,
    build_p144_preliminary_evidence,
)
from app.services.p144_runner import p144_release_case_catalog, run_p144_preliminary_matrix

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "evals/p144/input/provider-adapter-profile.json"
DEFAULT_OUTPUT = ROOT / "evals/p144/output"
DEFAULT_REVIEW = ROOT / "evals/p144/final-implementation-review.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preliminary", "final"), default="preliminary")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--canonical-matrix", type=Path, default=DEFAULT_OUTPUT / "canonical-matrix.json")
    parser.add_argument("--freeze-manifest", type=Path, default=DEFAULT_OUTPUT / "freeze-manifest.json")
    parser.add_argument("--final-review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args(argv)
    try:
        profile = _read_json(args.profile)
        if profile.get("cases") != p144_release_case_catalog():
            raise ValueError("p144_profile_catalog_drift")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = args.output_dir / "release-evidence.json"
        if args.mode == "preliminary":
            matrix = run_p144_preliminary_matrix(ROOT)
            manifest = build_p144_freeze_manifest(project_root=ROOT, profile=profile, matrix=matrix)
            evidence = build_p144_preliminary_evidence(matrix, manifest)
            _write_json(args.canonical_matrix, matrix)
            _write_json(args.freeze_manifest, manifest)
            _write_json(evidence_path, evidence)
        else:
            matrix_before = args.canonical_matrix.read_bytes()
            manifest_before = args.freeze_manifest.read_bytes()
            evidence = assemble_p144_final_evidence(
                _read_json(args.canonical_matrix),
                manifest=_read_json(args.freeze_manifest),
                review=_read_json(args.final_review),
                project_root=ROOT,
                profile=profile,
            )
            if args.canonical_matrix.read_bytes() != matrix_before or args.freeze_manifest.read_bytes() != manifest_before:
                raise ValueError("p144_final_mode_rewrote_frozen_input")
            _write_json(evidence_path, evidence)
        result = {
            "mode": args.mode,
            "status": evidence["status"],
            "passed": evidence["passed"],
            "failed": evidence["failed"],
            "evidence_hash": evidence["evidence_hash"],
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if args.mode == "preliminary" or evidence["status"] == P144_READY_STATUS else 1
    except Exception as exc:
        print(json.dumps({"status": P144_BLOCKED_STATUS, "error": str(exc), "error_type": type(exc).__name__}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
