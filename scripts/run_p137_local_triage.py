#!/usr/bin/env python3
"""Run the source-bound P137 local triage release qualification."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p137_release_evidence import (  # noqa: E402
    P137_READY_STATUS,
    assemble_p137_release_evidence_from_frozen_matrix,
    build_p137_freeze_manifest,
    p137_fixture_hash,
    p137_profile_hash,
    validate_final_implementation_review,
    validate_local_triage_profile,
)
from app.services.p137_runner import p137_release_case_matrix, run_p137_preliminary_matrix  # noqa: E402
from tests.fixtures.p137.builders import (  # noqa: E402
    P137_SOURCE_SCOPE,
    runtime_inputs as build_runtime_inputs,
)

DEFAULT_PROFILE = ROOT / "evals/p137/input/local-triage-profile.json"
DEFAULT_OUTPUT_DIR = ROOT / "evals/p137/output"
DEFAULT_FINAL_REVIEW = ROOT / "evals/p137/final-implementation-review.json"
DEFAULT_CANONICAL_MATRIX = DEFAULT_OUTPUT_DIR / "canonical-matrix.json"
DEFAULT_FREEZE_MANIFEST = DEFAULT_OUTPUT_DIR / "freeze-manifest.json"


class P137ProfileError(ValueError):
    """Raised when local P137 runner inputs are unavailable or unsafe."""


class CanonicalRuntimeFactory:
    """Build deterministic source-bound local scenarios for every P137 row."""

    def __init__(self, work_root: Path) -> None:
        self.work_root = work_root

    def __call__(self, case_id: str) -> Mapping[str, Any]:
        if case_id not in {str(item["case_id"]) for item in p137_release_case_matrix()}:
            raise P137ProfileError("unknown_case_id")
        return build_runtime_inputs(self.work_root / case_id, case_id)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preliminary", "final"), default="final")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--final-implementation-review", type=Path, default=DEFAULT_FINAL_REVIEW)
    parser.add_argument("--canonical-matrix", type=Path, default=DEFAULT_CANONICAL_MATRIX)
    parser.add_argument("--freeze-manifest", type=Path, default=DEFAULT_FREEZE_MANIFEST)
    args = parser.parse_args(argv)
    try:
        profile = validate_local_triage_profile(_read_json(args.profile))
        source_bindings = current_p137_source_hashes(ROOT)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.mode == "preliminary":
            with tempfile.TemporaryDirectory(prefix="p137-release-") as temporary:
                canonical_matrix = run_p137_preliminary_matrix(
                    args.output_dir,
                    runtime_factory=CanonicalRuntimeFactory(Path(temporary)),
                    evaluator_activity={
                        "runner_invocation_count": 1,
                        "profile_read_count": 1,
                        "handoff_fixture_write_count": 0,
                        "artifact_write_count": 2,
                        "fake_guard_callable_count": 0,
                        "child_process_count": 0,
                        "signal_delivery_count": 0,
                    },
                )
            freeze_manifest = build_p137_freeze_manifest(
                source_bindings=source_bindings,
                profile=profile,
                matrix_hash=canonical_matrix["matrix_hash"],
                case_input_hash=canonical_matrix["case_input_hash"],
                case_config_hash=canonical_matrix["case_config_hash"],
                case_evidence_hash=canonical_matrix["case_evidence_hash"],
                project_root=ROOT,
            )
            _write_json(args.canonical_matrix, canonical_matrix)
            _write_json(args.freeze_manifest, freeze_manifest)
            print(
                json.dumps(
                    {
                        "release_status": canonical_matrix["status"],
                        "mode": args.mode,
                        "matrix_hash": canonical_matrix["matrix_hash"],
                        "freeze_manifest_hash": freeze_manifest["freeze_manifest_hash"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0

        final_review = _validate_external_final_review(
            _read_json(args.final_implementation_review),
            expected_source_hashes=source_bindings,
        )
        evidence = assemble_p137_release_evidence_from_frozen_matrix(
            _read_json(args.canonical_matrix),
            freeze_manifest=_read_json(args.freeze_manifest),
            final_implementation_review=final_review,
            expected_source_hashes=source_bindings,
            expected_profile_hash=p137_profile_hash(profile),
            expected_fixture_hash=p137_fixture_hash(profile, project_root=ROOT),
        )
        _write_json(args.output_dir / "release-evidence.json", evidence)
        print(json.dumps({"release_status": evidence["status"], "mode": args.mode, "evidence_hash": evidence["evidence_hash"]}, sort_keys=True, separators=(",", ":")))
        return 0 if evidence["status"] == P137_READY_STATUS else 1
    except Exception as exc:
        print(json.dumps({"release_status": "p137_blocked", "error": str(exc), "error_type": type(exc).__name__}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1


def _read_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise P137ProfileError("invalid_json_object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")


def current_p137_source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    missing: list[str] = []
    for relative in P137_SOURCE_SCOPE:
        full = project_root / relative
        if not full.is_file():
            missing.append(relative)
            continue
        result[relative] = "sha256:" + hashlib.sha256(full.read_bytes()).hexdigest()
    if missing:
        raise P137ProfileError(f"source_scope_missing:{','.join(missing)}")
    return dict(sorted(result.items()))


def _validate_external_final_review(review: Mapping[str, Any], *, expected_source_hashes: Mapping[str, str]) -> dict[str, Any]:
    reviewer = str(review.get("reviewer_role", ""))
    implementer = str(review.get("implementation_role", ""))
    if not reviewer or reviewer == implementer or reviewer in {"implementation_agent", "opscat-release-builder", "p137_runner", "canonical_runtime_factory"}:
        raise P137ProfileError("final_review_must_be_external_to_implementation")
    return validate_final_implementation_review(review, expected_source_hashes=expected_source_hashes)


if __name__ == "__main__":
    raise SystemExit(main())
