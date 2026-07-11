#!/usr/bin/env python3
"""Render deterministic P109 real-ops benchmark release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p109_release_evidence import (  # noqa: E402
    DEFAULT_TRUSTED_NOW,
    P109_RELEASE_PROFILE,
    REVIEW_HASH_KEYS,
    build_p109_authority_scan,
    produce_p109_release_evidence,
    stable_hash,
    stable_json,
    write_p109_release_outputs,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline-default P109 real-ops benchmark release lane.")
    parser.add_argument("--benchmark-result", type=Path, required=True)
    parser.add_argument("--holdout-report", type=Path, required=True)
    parser.add_argument("--independent-review", type=Path)
    parser.add_argument("--output-json", type=Path, default=Path("/tmp/opscat-p109-real-ops-release.json"))
    parser.add_argument("--output-md", type=Path, default=Path("/tmp/opscat-p109-real-ops-release.md"))
    parser.add_argument("--producer-id", default="p109-producer")
    parser.add_argument("--dataset-mode", default="real", choices=("real", "authored_fixture"))
    parser.add_argument("--trusted-now", default=DEFAULT_TRUSTED_NOW)
    parser.add_argument("--release-profile-hash", default=None)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--raw-artifacts", type=Path)
    parser.add_argument("--normalized-corpus", type=Path)
    parser.add_argument("--diagnosis-report", type=Path)
    parser.add_argument("--remediation-report", type=Path)
    parser.add_argument("--contamination-report", type=Path)
    parser.add_argument("--authority-scan", type=Path)
    parser.add_argument("--release-profile", type=Path)
    parser.add_argument("--implementation-revision", type=Path)
    parser.add_argument("--real-release", action="store_true")
    parser.add_argument("--allow-network", action="store_true", help="Reserved opt-in flag; this lane does not perform network calls.")
    args = parser.parse_args(argv)

    benchmark_result = _read_json(args.benchmark_result)
    holdout_report = _read_json(args.holdout_report)
    independent_review = _read_json(args.independent_review) if args.independent_review is not None else None
    artifact_paths = _artifact_paths(args)
    missing_artifacts = [key for key, path in artifact_paths.items() if path is None]
    if args.real_release and missing_artifacts:
        raise ValueError(f"--real-release requires explicit artifact inputs: {', '.join(missing_artifacts)}")
    bound_artifact_hashes = _artifact_hashes_from_paths(artifact_paths)
    authority_scan = _read_json(args.authority_scan) if args.authority_scan is not None else build_p109_authority_scan()
    if args.release_profile is not None:
        profile_payload = _read_json(args.release_profile)
        release_profile_hash = bound_artifact_hashes["release_profile"]
    else:
        profile_payload = {
            "profile": P109_RELEASE_PROFILE,
            "passed": True,
            "fresh": True,
            "offline_default": not args.allow_network,
        }
        release_profile_hash = args.release_profile_hash or stable_hash(profile_payload)
    verify_profile = {**profile_payload, "release_profile_hash": release_profile_hash}
    evidence = produce_p109_release_evidence(
        producer_id=args.producer_id,
        benchmark_result=benchmark_result,
        holdout_report=holdout_report,
        authority_scan=authority_scan,
        verify_profile=verify_profile,
        independent_review=independent_review,
        bound_artifact_hashes=bound_artifact_hashes,
        dataset_mode=args.dataset_mode,
        trusted_now=args.trusted_now,
    )
    write_p109_release_outputs(evidence, output_json=args.output_json, output_md=args.output_md)
    sys.stdout.write(stable_json(evidence))
    if args.real_release and not evidence["release_qualified"]:
        return 1
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _artifact_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    return {
        "source_manifest": args.source_manifest,
        "raw_artifacts": args.raw_artifacts,
        "normalized_corpus": args.normalized_corpus,
        "diagnosis_report": args.diagnosis_report,
        "remediation_report": args.remediation_report,
        "contamination_report": args.contamination_report,
        "authority_scan": args.authority_scan,
        "release_profile": args.release_profile,
        "implementation_revision": args.implementation_revision,
    }


def _artifact_hashes_from_paths(paths: Mapping[str, Path | None]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, path in paths.items():
        if path is not None:
            hashes[key] = _file_hash(path)
    missing_keys = set(REVIEW_HASH_KEYS) - set(hashes) - {"release_evidence"}
    for key in missing_keys:
        hashes[key] = ""
    return hashes


def _file_hash(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError(f"artifact input does not exist or is not a file: {path}")
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
