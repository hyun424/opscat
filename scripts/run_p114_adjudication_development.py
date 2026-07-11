#!/usr/bin/env python3
"""Run gated, repeatable NVIDIA adjudication on a stratified consumed RE2-SS subset."""

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

from app.services.p110_candidate_runner import P110CandidateProvider  # noqa: E402
from app.services.p114_adjudicator import (  # noqa: E402
    NvidiaP114AdjudicatorProvider,
    P114AdjudicatorConfig,
    build_p114_adjudication_packet,
    nvidia_decoding_config,
    run_p114_adjudication,
)
from app.services.p114_hypothesis_lattice import FAULTS, build_p114_hypothesis_lattice  # noqa: E402
from app.services.p114_paired_evaluation import (  # noqa: E402
    evaluate_p114_paired_results,
    evaluate_p114_repeat_agreement,
    p114_adjudicator_development_gate,
)
from app.services.p114_re2_loader import P114RE2Case, load_pinned_re2_cases  # noqa: E402

DEFAULT_ARCHIVE = ROOT / "evals/real_datasets/external/p114/raw/RE2-SS.zip"
DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p114/source-manifest-re2-ss.json"
DEFAULT_HMAC_KEY = ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key"
DEFAULT_DEVELOPMENT_DIR = ROOT / "evals/real_datasets/external/p114/results/development"
DEFAULT_MODEL = "nvidia/nemotron-3-nano-30b-a3b"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--hmac-key", type=Path, default=DEFAULT_HMAC_KEY)
    parser.add_argument("--development-dir", type=Path, default=DEFAULT_DEVELOPMENT_DIR)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cases-per-fault", type=int, default=1)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    _load_env(args.env_file)
    try:
        gate = _read(args.development_dir / "candidate-gate-report.json")
        fused = _read(args.development_dir / "fused-evaluation.json")
        _validate_candidate_gate(gate, fused)
        cases = load_pinned_re2_cases(
            args.archive,
            args.manifest,
            hmac_key=args.hmac_key.read_bytes(),
        )
        selected = stratified_development_cases(cases, per_fault=args.cases_per_fault)
        provider = NvidiaP114AdjudicatorProvider(model=args.model)
        summary = run_adjudication_development(
            selected,
            provider=provider,
            model=args.model,
            runs=args.runs,
            output_dir=args.output_dir or args.development_dir / "adjudication",
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(2, f"p114_adjudication_development_failed:{exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


def stratified_development_cases(cases: Sequence[P114RE2Case], *, per_fault: int) -> tuple[P114RE2Case, ...]:
    if per_fault < 1:
        raise ValueError("invalid_cases_per_fault")
    selected: list[P114RE2Case] = []
    for fault in FAULTS:
        group = sorted(
            (case for case in cases if case.scorer_only_truth.get("fault_type") == fault),
            key=lambda case: case.case_id,
        )
        if len(group) < per_fault:
            raise ValueError(f"insufficient_fault_cases:{fault}")
        selected.extend(group[:per_fault])
    return tuple(sorted(selected, key=lambda case: case.case_id))


def run_adjudication_development(
    cases: Sequence[P114RE2Case],
    *,
    provider: P110CandidateProvider,
    model: str,
    runs: int,
    output_dir: str | Path,
) -> dict[str, Any]:
    if runs != 2:
        raise ValueError("exactly_two_runs_required")
    truths = [case.to_scorer_truth() for case in cases]
    candidates = [case.to_candidate_packet() for case in cases]
    lattices = [build_p114_hypothesis_lattice(packet) for packet in candidates]
    packets = [build_p114_adjudication_packet(candidate, lattice) for candidate, lattice in zip(candidates, lattices, strict=True)]
    config = P114AdjudicatorConfig(model=model, decoding_config=nvidia_decoding_config(model))
    result_sets = [[run_p114_adjudication(packet, provider=provider, config=config) for packet in packets] for _run_index in range(runs)]
    paired = [evaluate_p114_paired_results(truths, lattices, results) for results in result_sets]
    agreement = evaluate_p114_repeat_agreement(result_sets[0], result_sets[1])
    gate = p114_adjudicator_development_gate(paired, agreement)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for index, (results, report) in enumerate(zip(result_sets, paired, strict=True), start=1):
        _write(destination / f"run-{index}-results.json", {"results": results})
        _write(destination / f"run-{index}-paired-evaluation.json", report)
    _write(destination / "repeat-agreement.json", agreement)
    _write(destination / "development-gate.json", gate)
    summary = {
        "schema_version": "p114.adjudication_development_summary.v1",
        "benchmark_role": "consumed_development",
        "case_count": len(cases),
        "run_count": runs,
        "model": model,
        "paired_evaluation_hashes": [report["evaluation_hash"] for report in paired],
        "repeat_agreement_hash": agreement["agreement_hash"],
        "repeat_agreement": agreement["agreement"]["value"],
        "raw_contract_rates": [report["contract"]["raw_contract_rate"]["value"] for report in paired],
        "joint_top1_deltas": [report["delta"]["joint_top1"] for report in paired],
        "executed_action_count": sum(report["safety"]["executed_action_count"] for report in paired),
        "action_authority": "disabled",
        "development_gate_hash": gate["gate_hash"],
        "development_gates_passed": gate["passed"],
    }
    _write(destination / "summary.json", summary)
    return summary


def _validate_candidate_gate(gate: Mapping[str, Any], fused: Mapping[str, Any]) -> None:
    if gate.get("schema_version") != "p114.candidate_gate_report.v1" or gate.get("passed") is not True:
        raise ValueError("candidate_gate_not_passed")
    if str(gate.get("evaluation_hash", "")) != str(fused.get("evaluation_hash", "")):
        raise ValueError("candidate_gate_evaluation_mismatch")


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"not_json_object:{path.name}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
