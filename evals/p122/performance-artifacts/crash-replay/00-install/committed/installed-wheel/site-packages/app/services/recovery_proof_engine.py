"""P77 recovery proof engine.

P77 turns remediation post-check output into explicit recovery proof bundles.
It answers a narrower question than diagnosis: "is recovery actually proven by
local/mock evidence?" The engine is offline-only and never executes actions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value
from app.services.remediation_verification_loop import build_remediation_verification_loop_report

_BOUNDARY: dict[str, bool] = {
    "offline_fixture_only": True,
    "mock_or_draft_execution_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class RecoveryProofEngineReport:
    cases: tuple[dict[str, Any], ...]

    @classmethod
    def from_verification_cases(cls, cases: Sequence[Mapping[str, Any]]) -> Self:
        return cls(tuple(_proof_case(case) for case in cases))

    def to_dict(self) -> dict[str, Any]:
        case_count = len(self.cases)
        proven = sum(1 for case in self.cases if case["proof_status"] == "recovery_proven")
        not_proven = sum(1 for case in self.cases if case["proof_status"] == "recovery_not_proven")
        unsafe_blocked = sum(1 for case in self.cases if case["proof_status"] == "blocked_unsafe_execution")
        escalated = sum(1 for case in self.cases if case["operator_next_step"] == "escalate to incident commander")
        production_execution = sum(1 for case in self.cases if case["execution_boundary"]["production_execution_allowed"])
        action_execution = sum(1 for case in self.cases if case["execution_boundary"]["unsafe_action_allowed"])
        proof_scores = [float(case["proof_score"]) for case in self.cases]
        criteria_checked = sum(int(case["proof_bundle"]["criteria_checked_count"]) for case in self.cases)
        payload = {
            "summary": {
                "case_count": case_count,
                "recovery_proven_count": proven,
                "recovery_not_proven_count": not_proven,
                "blocked_unsafe_execution_count": unsafe_blocked,
                "escalation_required_count": escalated,
                "production_execution_count": production_execution,
                "action_execution_count": action_execution,
                "passed": case_count > 0
                and proven >= 1
                and not_proven >= 1
                and unsafe_blocked == 0
                and production_execution == 0
                and action_execution == 0,
            },
            "score": {
                "mean_proof_score": _mean(proof_scores),
                "minimum_proof_score": round(min(proof_scores), 3) if proof_scores else 0.0,
                "maximum_proof_score": round(max(proof_scores), 3) if proof_scores else 0.0,
                "criteria_checked_count": criteria_checked,
            },
            "boundary": dict(_BOUNDARY),
            "cases": list(self.cases),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_recovery_proof_engine_report(cases_path: str | Path) -> RecoveryProofEngineReport:
    verification_payload = build_remediation_verification_loop_report(cases_path).to_dict()
    cases = tuple(case for case in _sequence(verification_payload.get("cases", ())) if isinstance(case, Mapping))
    return RecoveryProofEngineReport.from_verification_cases(cases)


def render_recovery_proof_engine_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Recovery Proof Engine",
        "",
        "P77 proves or rejects recovery claims from local/mock post-check evidence bundles.",
        "",
        "## Summary",
        "",
        f"- Cases: {summary.get('case_count', 0)}",
        f"- Recovery proven: {summary.get('recovery_proven_count', 0)}",
        f"- Recovery not proven: {summary.get('recovery_not_proven_count', 0)}",
        f"- Escalation required: {summary.get('escalation_required_count', 0)}",
        f"- Blocked unsafe execution: {summary.get('blocked_unsafe_execution_count', 0)}",
        f"- Mean proof score: {score.get('mean_proof_score', 0.0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Proof bundles",
        "",
    ]
    for case in _sequence(payload.get("cases", ())):
        if isinstance(case, Mapping):
            bundle = _mapping(case.get("proof_bundle"))
            lines.append(
                f"- `{case.get('case_id')}` status={case.get('proof_status')} "
                f"score={case.get('proof_score')} passed={bundle.get('criteria_passed_count', 0)} "
                f"failed={bundle.get('criteria_failed_count', 0)}"
            )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Offline local/mock proof only.",
            "- No live APIs, credentials, network calls, production mutation, remediation execution, shell execution, or action execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_recovery_proof_engine_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_recovery_proof_engine_markdown(payload), encoding="utf-8")


def _proof_case(case: Mapping[str, Any]) -> dict[str, Any]:
    postcheck = _mapping(case.get("postcheck"))
    execution_boundary = _mapping(case.get("execution_boundary"))
    criteria = tuple(str(item) for item in _sequence(postcheck.get("criteria", ())))
    observed = _mapping(postcheck.get("observed"))
    passed_criteria, failed_criteria = _score_criteria(criteria, observed)
    unsafe = execution_boundary.get("production_execution_allowed") is True or execution_boundary.get("unsafe_action_allowed") is True
    expected_recovered = str(case.get("verification_status", "")) == "recovered"
    criteria_count = len(criteria)
    proof_score = _proof_score(criteria_count, len(passed_criteria), unsafe, expected_recovered)
    proof_status, reasons, next_step = _proof_status(
        unsafe=unsafe,
        expected_recovered=expected_recovered,
        failed_criteria=failed_criteria,
        criteria_count=criteria_count,
        proof_score=proof_score,
    )
    return {
        "case_id": str(case.get("case_id", case.get("id", "p77-case"))),
        "hypothesis": str(case.get("hypothesis", "unknown")),
        "proof_status": proof_status,
        "proof_score": proof_score,
        "reasons": reasons,
        "operator_next_step": next_step,
        "proof_bundle": {
            "criteria_checked_count": criteria_count,
            "criteria_passed_count": len(passed_criteria),
            "criteria_failed_count": len(failed_criteria),
            "passed_criteria": passed_criteria,
            "failed_criteria": failed_criteria,
            "observed": dict(observed),
        },
        "execution_boundary": {
            "production_execution_allowed": execution_boundary.get("production_execution_allowed") is True,
            "unsafe_action_allowed": execution_boundary.get("unsafe_action_allowed") is True,
        },
    }


def _score_criteria(criteria: Sequence[str], observed: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []
    for criterion in criteria:
        if _criterion_passed(criterion, observed):
            passed.append(criterion)
        else:
            failed.append(criterion)
    return passed, failed


def _criterion_passed(criterion: str, observed: Mapping[str, Any]) -> bool:
    checks = {
        "pool_wait_p95_below_500ms": _float(observed.get("pool_wait_p95_ms"), 999999.0) <= 500,
        "5xx_rate_below_1_percent": _float(observed.get("five_xx_rate"), 1.0) <= 0.01,
        "provider_timeout_rate_below_2_percent": _float(observed.get("provider_timeout_rate"), 1.0) <= 0.02,
        "checkout_error_rate_below_1_percent": _float(observed.get("checkout_error_rate"), 1.0) <= 0.01,
    }
    return checks.get(criterion, False)


def _proof_score(criteria_count: int, passed_count: int, unsafe: bool, expected_recovered: bool) -> float:
    if criteria_count <= 0:
        return 0.0
    score = 0.25 + 0.75 * (passed_count / criteria_count)
    if unsafe:
        score = 0.0
    return round(score, 3)


def _proof_status(
    *,
    unsafe: bool,
    expected_recovered: bool,
    failed_criteria: Sequence[str],
    criteria_count: int,
    proof_score: float,
) -> tuple[str, list[str], str]:
    if unsafe:
        return "blocked_unsafe_execution", ["unsafe execution boundary"], "escalate to incident commander"
    if criteria_count <= 0:
        return "recovery_not_proven", ["missing recovery criteria"], "escalate to incident commander"
    if expected_recovered and not failed_criteria and proof_score >= 0.85:
        return "recovery_proven", ["all recovery criteria passed"], "continue read-only monitoring"
    return "recovery_not_proven", ["post-check did not prove recovery"], "escalate to incident commander"


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


__all__ = [
    "RecoveryProofEngineReport",
    "build_recovery_proof_engine_report",
    "render_recovery_proof_engine_markdown",
    "write_recovery_proof_engine_outputs",
]
