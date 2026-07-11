#!/usr/bin/env python3
"""Parse the pinned real RCAEval/Baro sample without inventing ground truth."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p109_release_evidence import stable_hash, stable_json, zero_authority_counters  # noqa: E402
from app.services.rcaeval_adapter import load_rcaeval_cases  # noqa: E402

DEFAULT_SAMPLE = ROOT / "evals/real_datasets/external/p109/simple_data.csv"
DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p109/source-manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the pinned real RCAEval metric sample offline.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)

    manifest = _read_mapping(args.manifest)
    artifact = _artifact_for_path(manifest, args.source.name)
    revision = str(artifact["revision"])
    case = load_rcaeval_cases(args.source, source_revision=revision)[0]
    observations = case.candidate_visible_evidence
    actual_hash = case.raw_hashes[args.source.name]
    expected_hash = str(artifact["sha256"])
    if actual_hash != expected_hash:
        raise ValueError("real sample SHA-256 does not match the pinned manifest")

    services = sorted({str(item.get("service", "unknown")) for item in observations})
    metrics = sorted({str(item.get("metric", "unknown")) for item in observations})
    core: dict[str, Any] = {
        "schema_version": "p109.rcaeval_real_sample_smoke.v1",
        "source_id": artifact["source_id"],
        "source_revision": revision,
        "source_sha256": actual_hash,
        "observation_count": len(observations),
        "service_count": len(services),
        "metric_count": len(metrics),
        "services": services,
        "time_range": dict(case.time_range),
        "truth_available": case.truth_available,
        "real_telemetry_smoke_only": case.real_telemetry_smoke_only,
        "release_qualified": False,
        "status": "unevaluable_real_data_missing",
        "authority": zero_authority_counters(),
    }
    report = {**core, "report_hash": stable_hash(core)}
    rendered = stable_json(report)
    if args.output_json is not None:
        args.output_json.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


def _read_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def _artifact_for_path(manifest: dict[str, Any], filename: str) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("manifest artifacts must be a list")
    for value in artifacts:
        if isinstance(value, dict) and filename in value.get("expected_paths", []):
            return value
    raise ValueError(f"manifest does not bind {filename}")


if __name__ == "__main__":
    raise SystemExit(main())
