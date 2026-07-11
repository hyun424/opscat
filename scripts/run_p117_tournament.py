#!/usr/bin/env python3
"""Run and seal the frozen offline P117 action-selection tournament."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p117_benchmark import run_p117_deterministic_tournament  # noqa: E402
from app.services.p117_evidence_acquisition import EVIDENCE_TAXONOMY_HASH  # noqa: E402
from app.services.p117_release_evidence import empty_p117_authority_counters, produce_p117_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p115-release", type=Path, required=True)
    parser.add_argument("--p116-release", type=Path, required=True)
    parser.add_argument("--p116-outcomes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=11701)
    parser.add_argument("--reviewer-id", default="independent-verifier")
    parser.add_argument("--builder-id", default="autonomous-builder")
    args = parser.parse_args(argv)

    p115 = _read(args.p115_release)
    p116 = _read(args.p116_release)
    p116_outcomes = _read(args.p116_outcomes)
    run = run_p117_deterministic_tournament(p116_release_evidence=p116_outcomes, frozen_seed=args.seed)
    frozen_configuration = {
        "seed": args.seed,
        "selector": "p117-deterministic-v1",
        "calibration_confidence": 0.98,
        "calibration_threshold": 0.70,
        "utility_threshold": 0.0,
        "evidence_taxonomy_hash": EVIDENCE_TAXONOMY_HASH,
        "nvidia_mode": "parser_only_not_scored",
    }
    upstream = {
        "p114": stable_hash(_mapping(run["episode_manifest"]).get("p114_lattices", [])),
        "p115": str(p115.get("release_evidence_hash", "")),
        "p116": str(p116.get("release_evidence_hash", "")),
        "p116_outcomes": str(p116_outcomes.get("release_evidence_hash", "")),
    }
    release = produce_p117_release_evidence(
        episode_manifest=_mapping(run["episode_manifest"]),
        tournament_report=_mapping(run["tournament_report"]),
        replay_report=_mapping(run["replay_report"]),
        frozen_configuration=frozen_configuration,
        upstream_manifest=upstream,
        reviewer_identity={"id": args.reviewer_id},
        builder_identity={"id": args.builder_id},
        authority_counters=empty_p117_authority_counters(),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "episode-manifest.json": run["episode_manifest"],
        "evaluator-only-hidden-labels.json": {
            "schema_version": "p117.evaluator_labels.v1",
            "labels": run["hidden_labels"],
            "labels_hash": stable_hash(run["hidden_labels"]),
        },
        "tournament-report.json": run["tournament_report"],
        "replay-report.json": run["replay_report"],
        "release-evidence.json": release,
    }
    for name, value in artifacts.items():
        _atomic_write(args.output_dir / name, value)
    print(
        json.dumps(
            {
                "release_status": release["release_status"],
                "outcome_qualified": release["outcome_qualified"],
                "release_evidence_hash": release["release_evidence_hash"],
                "episode_count": release["episode_manifest"]["episode_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if release["outcome_qualified"] is True else 1


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SystemExit(f"expected JSON object: {path}")
    return dict(value)


def _atomic_write(path: Path, value: Any) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


if __name__ == "__main__":
    raise SystemExit(main())
