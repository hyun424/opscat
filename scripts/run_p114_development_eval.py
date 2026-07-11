#!/usr/bin/env python3
"""Evaluate deterministic P114 candidate generation on consumed RE2 development data."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p114_development_evaluation import (  # noqa: E402
    evaluate_p114_development_lattices,
    p114_candidate_gate_report,
)
from app.services.p114_hypothesis_lattice import build_p114_hypothesis_lattice  # noqa: E402
from app.services.p114_re2_loader import load_pinned_re2_cases  # noqa: E402

DEFAULT_ARCHIVE = ROOT / "evals/real_datasets/external/p114/raw/RE2-SS.zip"
DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p114/source-manifest-re2-ss.json"
DEFAULT_HMAC_KEY = ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key"
DEFAULT_OUTPUT_DIR = ROOT / "evals/real_datasets/external/p114/results/development"
MODALITIES = ("fused", "metric", "log_template")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--hmac-key", type=Path, default=DEFAULT_HMAC_KEY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--max-hypotheses", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        summary = run_development_evaluation(
            args.archive,
            args.manifest,
            hmac_key=args.hmac_key.read_bytes(),
            output_dir=args.output_dir,
            max_cases=args.max_cases,
            max_hypotheses=args.max_hypotheses,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"p114_development_eval_failed:{exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


def run_development_evaluation(
    archive: str | Path,
    manifest: str | Path,
    *,
    hmac_key: bytes,
    output_dir: str | Path,
    max_cases: int | None = None,
    max_hypotheses: int = 30,
) -> dict[str, Any]:
    cases = load_pinned_re2_cases(archive, manifest, hmac_key=hmac_key, max_cases=max_cases)
    truths = [case.to_scorer_truth() for case in cases]
    packets = [case.to_candidate_packet() for case in cases]
    reports: dict[str, Mapping[str, Any]] = {}
    lattices_by_modality: dict[str, list[dict[str, Any]]] = {}
    for modality in MODALITIES:
        modality_packets = [_packet_for_modality(packet, modality) for packet in packets]
        lattices = [build_p114_hypothesis_lattice(packet, max_hypotheses=max_hypotheses) for packet in modality_packets]
        lattices_by_modality[modality] = lattices
        reports[modality] = evaluate_p114_development_lattices(truths, lattices, modality=modality)

    fused_gate = p114_candidate_gate_report(reports["fused"])
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for modality, report in reports.items():
        _write(destination / f"{modality}-evaluation.json", report)
        _write(destination / f"{modality}-lattices.json", {"lattices": lattices_by_modality[modality]})
    _write(destination / "candidate-gate-report.json", fused_gate)
    summary = {
        "schema_version": "p114.development_run_summary.v1",
        "benchmark_role": "consumed_development",
        "case_count": len(cases),
        "modalities": list(MODALITIES),
        "fused_evaluation_hash": reports["fused"]["evaluation_hash"],
        "candidate_gate_report_hash": fused_gate["gate_report_hash"],
        "candidate_gates_passed": fused_gate["passed"],
        "action_authority": "disabled",
    }
    _write(destination / "run-summary.json", summary)
    return summary


def _packet_for_modality(packet: Mapping[str, Any], modality: str) -> dict[str, Any]:
    if modality not in MODALITIES:
        raise ValueError("invalid_modality")
    cloned = json.loads(json.dumps(packet, sort_keys=True, allow_nan=False))
    if modality == "fused":
        return cloned
    graph = cloned["evidence_graph"]
    nodes = [node for node in graph["nodes"] if node["modality"] == modality]
    node_ids = {node["node_id"] for node in nodes}
    edges = [edge for edge in graph["edges"] if edge["source_node_id"] in node_ids and edge["target_node_id"] in node_ids]
    if not nodes:
        raise ValueError(f"missing_modality_evidence:{modality}")
    graph["nodes"] = nodes
    graph["edges"] = edges
    return cloned


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
