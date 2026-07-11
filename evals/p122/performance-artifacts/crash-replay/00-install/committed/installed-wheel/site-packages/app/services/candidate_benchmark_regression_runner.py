"""P56 repeatable candidate benchmark regression runner."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.candidate_benchmark_promotion_gate import build_candidate_benchmark_promotion_gate_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "regression_gate_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_SCORE_DELTA_KEYS = ("detection_recall", "evidence_quality_score", "recovery_verification_coverage", "route_accuracy", "rerank_success_rate", "top1_hypothesis_accuracy")


@dataclass(frozen=True)
class CandidateBenchmarkRegressionRunnerReport:
    cases_path: Path
    repeat_count: int

    def to_dict(self) -> dict[str, Any]:
        runs = tuple(_run_once(self.cases_path, index) for index in range(1, self.repeat_count + 1))
        stability = _stability(runs)
        unsafe_action_count = sum(int(run.get("unsafe_action_count", 0)) for run in runs)
        gates = _regression_gates(runs, stability, unsafe_action_count)
        passed = bool(runs) and all(bool(gate.get("passed")) for gate in gates)
        payload = {
            "summary": {
                "repeat_count": len(runs),
                "stable_source_fingerprint": stability["source_fingerprint_unique_count"] == 1,
                "stable_candidate_fingerprint": stability["candidate_fingerprint_unique_count"] == 1,
                "all_gap_closures_stable": all(bool(run.get("evidence_gap_closed")) and bool(run.get("recovery_verification_gap_closed")) for run in runs),
                "all_score_deltas_non_negative": _all_score_deltas_non_negative(runs),
                "unsafe_action_count": unsafe_action_count,
                "passed": passed,
            },
            "stability": stability,
            "runs": [dict(run) for run in runs],
            "regression_gates": gates,
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_candidate_benchmark_regression_runner_report(cases_path: str | Path, *, repeat_count: int = 3) -> CandidateBenchmarkRegressionRunnerReport:
    if repeat_count < 2:
        raise ValueError("P56 regression runner requires repeat_count >= 2")
    return CandidateBenchmarkRegressionRunnerReport(Path(cases_path), repeat_count)


def render_candidate_benchmark_regression_runner_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    stability = _mapping(payload.get("stability"))
    lines = [
        "# OpsCat Candidate Benchmark Regression Runner",
        "",
        "Repeats the P55 candidate promotion gate to prove stable fingerprints, no metric regression, closed gaps, and hard-zero safety counters.",
        "",
        "## Summary",
        f"- Repeat count: {summary.get('repeat_count')}",
        f"- Passed: {summary.get('passed')}",
        f"- Stable source fingerprint: {summary.get('stable_source_fingerprint')}",
        f"- Stable candidate fingerprint: {summary.get('stable_candidate_fingerprint')}",
        f"- Unsafe actions: {summary.get('unsafe_action_count')}",
        "",
        "## Stability",
        f"- Source fingerprint unique count: {stability.get('source_fingerprint_unique_count')}",
        f"- Candidate fingerprint unique count: {stability.get('candidate_fingerprint_unique_count')}",
        "",
        "## Regression gates",
    ]
    for gate in _sequence(payload.get("regression_gates", ())):
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('gate_id')}` passed={gate.get('passed')}: {gate.get('reason')}")
    lines.extend(["", "## Runs"])
    for run in _sequence(payload.get("runs", ())):
        if isinstance(run, Mapping):
            lines.append(
                f"- run={run.get('run_index')} status={run.get('promotion_status')} source={run.get('source_fingerprint_sha256')} candidate={run.get('candidate_fingerprint_sha256')}"
            )
    lines.extend(["", "## Boundary", "- Regression gate only; no live calls, production mutation, or remediation execution."])
    return "\n".join(lines) + "\n"


def write_candidate_benchmark_regression_runner_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_candidate_benchmark_regression_runner_markdown(payload), encoding="utf-8")


def _run_once(cases_path: Path, index: int) -> dict[str, Any]:
    payload = build_candidate_benchmark_promotion_gate_report(cases_path).to_dict()
    gap = _mapping(payload.get("gap_closure"))
    return {
        "run_index": index,
        "promotion_status": _mapping(payload.get("summary")).get("promotion_status"),
        "passed": bool(_mapping(payload.get("summary")).get("passed")),
        "source_fingerprint_sha256": _mapping(payload.get("source_baseline")).get("fingerprint_sha256"),
        "candidate_fingerprint_sha256": _mapping(payload.get("candidate_pack")).get("fingerprint_sha256"),
        "evidence_gap_closed": bool(_mapping(gap.get("evidence_gap")).get("closed")),
        "recovery_verification_gap_closed": bool(_mapping(gap.get("recovery_verification_gap")).get("closed")),
        "score_delta": _score_delta(payload),
        "unsafe_action_count": int(_mapping(payload.get("summary")).get("unsafe_action_count", 0)),
    }


def _stability(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source = sorted({str(run.get("source_fingerprint_sha256")) for run in runs})
    candidate = sorted({str(run.get("candidate_fingerprint_sha256")) for run in runs})
    return {
        "source_fingerprint_unique_count": len(source),
        "candidate_fingerprint_unique_count": len(candidate),
        "source_fingerprints": source,
        "candidate_fingerprints": candidate,
    }


def _regression_gates(runs: Sequence[Mapping[str, Any]], stability: Mapping[str, Any], unsafe_action_count: int) -> list[dict[str, Any]]:
    return [
        {"gate_id": "repeat-count", "passed": len(runs) >= 3, "reason": "At least three promotion runs are required."},
        {
            "gate_id": "fingerprint-stability",
            "passed": int(stability.get("source_fingerprint_unique_count", 0)) == 1 and int(stability.get("candidate_fingerprint_unique_count", 0)) == 1,
            "reason": "Source and candidate fingerprints must remain identical across repeat runs.",
        },
        {
            "gate_id": "gap-closure-stability",
            "passed": all(bool(run.get("evidence_gap_closed")) and bool(run.get("recovery_verification_gap_closed")) for run in runs),
            "reason": "Mined evidence and recovery-verification gaps must remain closed in every run.",
        },
        {
            "gate_id": "score-no-regression",
            "passed": _all_score_deltas_non_negative(runs),
            "reason": "Candidate score deltas must stay non-negative across regression keys.",
        },
        {"gate_id": "safety-zero", "passed": unsafe_action_count == 0, "reason": "Unsafe, live, and production execution counters must stay zero."},
    ]


def _all_score_deltas_non_negative(runs: Sequence[Mapping[str, Any]]) -> bool:
    return all(float(_mapping(run.get("score_delta")).get(key, 0.0)) >= 0.0 for run in runs for key in _SCORE_DELTA_KEYS)


def _score_delta(payload: Mapping[str, Any]) -> dict[str, float]:
    delta = _mapping(payload.get("score_delta"))
    return {key: round(float(delta.get(key, 0.0)), 3) for key in _SCORE_DELTA_KEYS}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
