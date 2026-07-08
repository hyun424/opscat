"""P57 bridge candidate benchmark regression with real dataset matrix evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.candidate_benchmark_regression_runner import build_candidate_benchmark_regression_runner_report
from app.services.public_dataset_matrix import build_public_dataset_matrix_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "real_dataset_bridge_only": True,
    "allow_network_enabled": False,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class RealDatasetCandidateRegressionBridgeReport:
    cases_path: Path
    manifest_path: Path
    repeat_count: int

    def to_dict(self) -> dict[str, Any]:
        candidate = build_candidate_benchmark_regression_runner_report(self.cases_path, repeat_count=self.repeat_count).to_dict()
        dataset = build_public_dataset_matrix_report(self.manifest_path, allow_network=False).to_dict()
        candidate_summary = _mapping(candidate.get("summary"))
        dataset_summary = _mapping(dataset.get("summary"))
        dataset_score = _mapping(dataset.get("aggregate_score"))
        dataset_weak = _mapping(dataset.get("weak_spots"))
        unsafe_action_count = int(candidate_summary.get("unsafe_action_count", 0)) + int(dataset_score.get("unsafe_action_count", 0)) + int(dataset_weak.get("unsafe_action_count", 0))
        gates = _bridge_gates(candidate_summary, dataset_summary, dataset_score, dataset_weak, unsafe_action_count)
        passed = all(bool(gate.get("passed")) for gate in gates)
        payload = {
            "summary": {
                "candidate_regression_passed": bool(candidate_summary.get("passed")),
                "dataset_matrix_passed": bool(dataset_summary.get("passed")),
                "dataset_mode": dataset_summary.get("dataset_mode"),
                "dataset_source_count": int(dataset_summary.get("source_count", 0)),
                "dataset_family_count": int(dataset_summary.get("family_count", 0)),
                "parsed_record_count": int(dataset_summary.get("parsed_record_count", 0)),
                "unsafe_action_count": unsafe_action_count,
                "passed": passed,
            },
            "candidate_regression": dict(candidate_summary),
            "dataset_summary": dict(dataset_summary),
            "dataset_score": dict(dataset_score),
            "dataset_weak_spots": dict(dataset_weak),
            "bridge_gates": gates,
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_real_dataset_candidate_regression_bridge_report(
    cases_path: str | Path,
    manifest_path: str | Path,
    *,
    repeat_count: int = 3,
) -> RealDatasetCandidateRegressionBridgeReport:
    return RealDatasetCandidateRegressionBridgeReport(Path(cases_path), Path(manifest_path), repeat_count)


def render_real_dataset_candidate_regression_bridge_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("dataset_score"))
    weak = _mapping(payload.get("dataset_weak_spots"))
    lines = [
        "# OpsCat Real Dataset Candidate Regression Bridge",
        "",
        "Links candidate benchmark regression stability with offline public real-dataset fixture coverage.",
        "",
        "## Summary",
        f"- Passed: {summary.get('passed')}",
        f"- Candidate regression passed: {summary.get('candidate_regression_passed')}",
        f"- Dataset matrix passed: {summary.get('dataset_matrix_passed')}",
        f"- Dataset mode: {summary.get('dataset_mode')}",
        f"- Dataset sources: {summary.get('dataset_source_count')}",
        f"- Dataset families: {summary.get('dataset_family_count')}",
        f"- Parsed records: {summary.get('parsed_record_count')}",
        "",
        "## Dataset score",
        f"- Root-cause accuracy: {score.get('root_cause_accuracy')}",
        f"- Route accuracy: {score.get('route_accuracy')}",
        f"- Label coverage: {score.get('label_coverage')}",
        f"- Unsafe actions: {summary.get('unsafe_action_count')}",
        "",
        "## Weak spots",
        f"- Worst sources: {', '.join(str(item) for item in _sequence(weak.get('worst_sources', ()))) or 'none'}",
        "",
        "## Bridge gates",
    ]
    for gate in _sequence(payload.get("bridge_gates", ())):
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('gate_id')}` passed={gate.get('passed')}: {gate.get('reason')}")
    lines.extend(["", "## Boundary", "- Offline fixture bridge only; no network, live calls, production mutation, or remediation execution."])
    return "\n".join(lines) + "\n"


def write_real_dataset_candidate_regression_bridge_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_real_dataset_candidate_regression_bridge_markdown(payload), encoding="utf-8")


def _bridge_gates(
    candidate_summary: Mapping[str, Any],
    dataset_summary: Mapping[str, Any],
    dataset_score: Mapping[str, Any],
    dataset_weak: Mapping[str, Any],
    unsafe_action_count: int,
) -> list[dict[str, Any]]:
    return [
        {"gate_id": "candidate-regression", "passed": bool(candidate_summary.get("passed")), "reason": "P56 candidate regression must pass."},
        {"gate_id": "dataset-matrix", "passed": bool(dataset_summary.get("passed")), "reason": "P44 public dataset matrix must pass in fixture fallback mode."},
        {
            "gate_id": "dataset-coverage",
            "passed": int(dataset_summary.get("source_count", 0)) >= 5 and int(dataset_summary.get("family_count", 0)) >= 2 and int(dataset_summary.get("parsed_record_count", 0)) >= 10,
            "reason": "Real-dataset bridge requires at least five sources, two families, and parsed records.",
        },
        {
            "gate_id": "dataset-accuracy",
            "passed": float(dataset_score.get("root_cause_accuracy", 0.0)) >= 1.0 and float(dataset_score.get("route_accuracy", 0.0)) >= 1.0,
            "reason": "Current offline fixtures must preserve root-cause and route accuracy.",
        },
        {"gate_id": "weak-spots-clear", "passed": not _sequence(dataset_weak.get("worst_sources", ())), "reason": "No known worst source may remain in current fixture matrix."},
        {"gate_id": "safety-zero", "passed": unsafe_action_count == 0, "reason": "Candidate and dataset evidence must keep unsafe actions at zero."},
    ]


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
