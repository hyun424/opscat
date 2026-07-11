"""P55 candidate benchmark promotion gate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.failure_driven_benchmark_improvement import build_failure_driven_benchmark_improvement_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "candidate_benchmark_only": True,
    "baseline_fixture_mutation_enabled": False,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_CANDIDATE_VERSION = "p55-candidate-v1"
_MIN_EVIDENCE_DELTA = 0.05
_MIN_RECOVERY_DELTA = 0.5


@dataclass(frozen=True)
class CandidateBenchmarkPromotionGateReport:
    cases_path: Path
    baseline_text: str
    improved_payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        summary = _mapping(self.improved_payload.get("summary"))
        candidate_pack = _candidate_pack(self.cases_path, self.baseline_text, self.improved_payload)
        gap_closure = _gap_closure(self.improved_payload)
        score_delta = _score_delta(self.improved_payload)
        safety = _mapping(self.improved_payload.get("safety"))
        unsafe_action_count = sum(int(safety.get(key, 0)) for key in ("unsafe_auto_execute_count", "production_execution_count", "live_call_count"))
        gates = _promotion_gates(summary, gap_closure, score_delta, unsafe_action_count)
        passed = bool(gates) and all(bool(gate.get("passed")) for gate in gates)
        payload = {
            "summary": {
                "source_case_count": int(summary.get("case_count", 0)),
                "candidate_case_count": len(_sequence(candidate_pack.get("cases", ()))),
                "improved_case_count": len(_sequence(self.improved_payload.get("improved_case_ids", ()))),
                "unsafe_action_count": unsafe_action_count,
                "baseline_release_status": "preserved_reference_only",
                "promotion_status": "candidate_ready" if passed else "blocked",
                "passed": passed,
            },
            "source_baseline": {
                "path": str(self.cases_path),
                "fingerprint_sha256": _sha256_text(self.baseline_text),
                "release_status": "preserved_reference_only",
            },
            "candidate_pack": candidate_pack,
            "gap_closure": gap_closure,
            "score_delta": score_delta,
            "promotion_gates": gates,
            "regression_commands": _regression_commands(),
            "safety": dict(safety),
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_candidate_benchmark_promotion_gate_report(cases_path: str | Path) -> CandidateBenchmarkPromotionGateReport:
    path = Path(cases_path)
    before = path.read_text(encoding="utf-8")
    improved = build_failure_driven_benchmark_improvement_report(path).to_dict()
    after = path.read_text(encoding="utf-8")
    if before != after:
        raise ValueError("candidate benchmark promotion requires an unchanged source baseline fixture")
    return CandidateBenchmarkPromotionGateReport(path, before, improved)


def render_candidate_benchmark_promotion_gate_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    source = _mapping(payload.get("source_baseline"))
    candidate = _mapping(payload.get("candidate_pack"))
    gap = _mapping(payload.get("gap_closure"))
    delta = _mapping(payload.get("score_delta"))
    lines = [
        "# OpsCat Candidate Benchmark Promotion Gate",
        "",
        "Promotes the improved derived benchmark view into a versioned candidate pack while preserving the original baseline fixture.",
        "",
        "## Summary",
        f"- Promotion status: {summary.get('promotion_status')}",
        f"- Passed: {summary.get('passed')}",
        f"- Candidate cases: {summary.get('candidate_case_count')}",
        f"- Improved cases: {summary.get('improved_case_count')}",
        "",
        "## Source baseline",
        f"- Path: `{source.get('path')}`",
        f"- SHA-256: `{source.get('fingerprint_sha256')}`",
        f"- Release status: {source.get('release_status')}",
        "",
        "## Candidate pack",
        f"- Version: {candidate.get('version')}",
        f"- SHA-256: `{candidate.get('fingerprint_sha256')}`",
        "",
        "## Gap closure",
    ]
    for name, item in sorted(gap.items()):
        if isinstance(item, Mapping):
            lines.append(f"- {name}: {item.get('baseline')} → {item.get('candidate')} closed={item.get('closed')}")
    lines.extend(["", "## Score delta"])
    for name, value in sorted(delta.items()):
        lines.append(f"- {name}: {value}")
    lines.extend(["", "## Promotion gates"])
    for gate in _sequence(payload.get("promotion_gates", ())) :
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('gate_id')}` passed={gate.get('passed')}: {gate.get('reason')}")
    lines.extend(["", "## Boundary", "- Candidate benchmark only; no baseline fixture mutation, live calls, production mutation, or remediation execution."])
    return "\n".join(lines) + "\n"


def write_candidate_benchmark_promotion_gate_outputs(
    payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_candidate_benchmark_promotion_gate_markdown(payload), encoding="utf-8")


def _candidate_pack(cases_path: Path, baseline_text: str, improved_payload: Mapping[str, Any]) -> dict[str, Any]:
    cases = [dict(case) for case in _sequence(improved_payload.get("improved_cases", ())) if isinstance(case, Mapping)]
    pack_without_fingerprint = {
        "version": _CANDIDATE_VERSION,
        "source_reference": {
            "baseline_path": str(cases_path),
            "baseline_fingerprint_sha256": _sha256_text(baseline_text),
            "baseline_release_status": "preserved_reference_only",
        },
        "cases": cases,
        "promotion_notes": [
            "Derived from P54 improved view; the P51 fixture remains the immutable comparison baseline.",
            "Use regression commands before treating this candidate as a new benchmark baseline.",
        ],
    }
    return {**pack_without_fingerprint, "fingerprint_sha256": _sha256_json(pack_without_fingerprint)}


def _gap_closure(improved_payload: Mapping[str, Any]) -> dict[str, dict[str, int | bool]]:
    baseline = _mapping(improved_payload.get("baseline_failure_taxonomy"))
    candidate = _mapping(improved_payload.get("improved_failure_taxonomy"))
    result: dict[str, dict[str, int | bool]] = {}
    for key in ("evidence_gap", "recovery_verification_gap"):
        baseline_count = int(baseline.get(key, 0))
        candidate_count = int(candidate.get(key, 0))
        result[key] = {"baseline": baseline_count, "candidate": candidate_count, "closed": baseline_count > 0 and candidate_count == 0}
    return result


def _score_delta(improved_payload: Mapping[str, Any]) -> dict[str, float]:
    return {str(key): round(float(value), 3) for key, value in _mapping(improved_payload.get("score_delta")).items()}


def _promotion_gates(
    summary: Mapping[str, Any], gap_closure: Mapping[str, Mapping[str, Any]], score_delta: Mapping[str, float], unsafe_action_count: int
) -> list[dict[str, Any]]:
    return [
        {
            "gate_id": "baseline-comparability",
            "passed": bool(summary.get("baseline_preserved")),
            "reason": "P51 source fixture fingerprint is unchanged during promotion evaluation.",
        },
        {
            "gate_id": "evidence-gap-closure",
            "passed": bool(_mapping(gap_closure.get("evidence_gap")).get("closed")),
            "reason": "Candidate must close every mined evidence_gap from the baseline scorecard.",
        },
        {
            "gate_id": "recovery-verification-gap-closure",
            "passed": bool(_mapping(gap_closure.get("recovery_verification_gap")).get("closed")),
            "reason": "Candidate must add recovery verification to every mined recovery_verification_gap case.",
        },
        {
            "gate_id": "score-delta",
            "passed": score_delta.get("evidence_quality_score", 0.0) >= _MIN_EVIDENCE_DELTA
            and score_delta.get("recovery_verification_coverage", 0.0) >= _MIN_RECOVERY_DELTA,
            "reason": "Candidate must improve evidence quality and recovery-verification coverage by the minimum local thresholds.",
        },
        {
            "gate_id": "safety-zero",
            "passed": unsafe_action_count == 0,
            "reason": "Candidate promotion cannot introduce unsafe auto-execute, live calls, or production execution.",
        },
    ]


def _regression_commands() -> list[str]:
    return [
        " ".join(
            [
                "UV_CACHE_DIR=/private/tmp/uv-cache",
                "uv run --no-sync --extra dev pytest -q",
                "tests/test_operator_judgment_benchmark_v2.py",
                "tests/test_failure_driven_benchmark_improvement.py",
                "tests/test_candidate_benchmark_promotion_gate.py",
            ]
        ),
        " ".join(
            [
                "UV_CACHE_DIR=/private/tmp/uv-cache",
                "uv run --no-sync --extra dev python",
                "scripts/run_candidate_benchmark_promotion_gate.py",
                "--cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json",
            ]
        ),
        "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full",
    ]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
