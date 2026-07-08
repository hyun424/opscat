"""P49 remediation verification loop with production execution disabled."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "mock_or_draft_execution_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class RemediationVerificationLoopReport:
    cases: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        precheck_pass = sum(1 for case in self.cases if case["precheck"]["passed"])
        recovered = sum(1 for case in self.cases if case["verification_status"] == "recovered")
        escalated = sum(1 for case in self.cases if case["verification_status"] != "recovered" and case["rollback_or_escalation"])
        production_execution = sum(1 for case in self.cases if case["execution_boundary"]["production_execution_allowed"])
        unsafe = sum(1 for case in self.cases if case["execution_boundary"]["unsafe_action_allowed"])
        payload = {
            "summary": {
                "case_count": len(self.cases),
                "precheck_pass_count": precheck_pass,
                "recovery_verified_count": recovered,
                "failed_verification_escalation_count": escalated,
                "production_execution_count": production_execution,
                "unsafe_action_count": unsafe,
                "passed": bool(self.cases) and precheck_pass >= 1 and recovered >= 1 and escalated >= 1 and production_execution == 0 and unsafe == 0,
            },
            "boundary": dict(_BOUNDARY),
            "cases": list(self.cases),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_remediation_verification_loop_report(cases_path: str | Path) -> RemediationVerificationLoopReport:
    return RemediationVerificationLoopReport(tuple(_verify_case(case) for case in _load_cases(cases_path)))


def render_remediation_verification_loop_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Remediation Verification Loop",
        "",
        "Verifies remediation proposals with pre-checks, mock/draft execution boundaries, post-checks, and escalation when recovery is not proven.",
        "",
        "## Summary",
        f"- Cases: {summary.get('case_count')}",
        f"- Pre-check passed: {summary.get('precheck_pass_count')}",
        f"- Recovery verified: {summary.get('recovery_verified_count')}",
        f"- Failed verification escalations: {summary.get('failed_verification_escalation_count')}",
        f"- Production execution count: {summary.get('production_execution_count')}",
        "",
        "## Cases",
    ]
    for case in _sequence(payload.get("cases", ())) :
        if isinstance(case, Mapping):
            lines.append(f"- `{case.get('case_id')}` status={case.get('verification_status')}")
            lines.append(f"  - Pre-check: {case.get('precheck')}")
            lines.append(f"  - Post-check: {case.get('postcheck')}")
            lines.append(f"  - Rollback/escalation: {case.get('rollback_or_escalation')}")
    lines.extend(["", "## Boundary", "- Production execution remains disabled; actions are mock/draft evidence only."])
    return "\n".join(lines) + "\n"


def write_remediation_verification_loop_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_remediation_verification_loop_markdown(payload), encoding="utf-8")


def _load_cases(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P49 cases must be a mapping")
    return tuple(item for item in _sequence(data.get("cases", ())) if isinstance(item, Mapping))


def _verify_case(case: Mapping[str, Any]) -> dict[str, Any]:
    precheck = _precheck(_mapping(case.get("precheck")))
    postcheck = _postcheck(_mapping(case.get("postcheck")))
    status = postcheck["status"] if precheck["passed"] else "precheck_failed"
    rollback_or_escalation = _rollback_or_escalation(status, precheck)
    return {
        "case_id": str(case.get("id", "p49-case")),
        "hypothesis": str(case.get("hypothesis", "unknown")),
        "confidence": _float(case.get("confidence"), 0.0),
        "proposed_action": str(case.get("proposed_action", "draft remediation")),
        "precheck": precheck,
        "execution_boundary": {
            "mode": "mock_only" if precheck["passed"] else "blocked",
            "production_execution_allowed": False,
            "unsafe_action_allowed": False,
            "approval_required": True,
            "blocked_actions": ["execute production change", "restart production", "rollback production", "write config"],
        },
        "postcheck": postcheck,
        "verification_status": status,
        "rollback_or_escalation": rollback_or_escalation,
    }


def _precheck(precheck: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in ("blast_radius", "rollback_plan", "approval", "safe_mode") if not precheck.get(field)]
    passed = bool(precheck.get("passed")) and not missing and str(precheck.get("safe_mode")) == "mock_only"
    return {
        "passed": passed,
        "missing": missing,
        "blast_radius": str(precheck.get("blast_radius", "unknown")),
        "rollback_plan": str(precheck.get("rollback_plan", "escalate to human")),
        "approval": str(precheck.get("approval", "required")),
        "safe_mode": str(precheck.get("safe_mode", "mock_only")),
    }


def _postcheck(postcheck: Mapping[str, Any]) -> dict[str, Any]:
    observed = _mapping(postcheck.get("observed"))
    expected = str(postcheck.get("expected_status", "not_recovered"))
    criteria = [str(item) for item in _sequence(postcheck.get("criteria", ()))]
    derived = _derive_status(observed)
    status = "recovered" if expected == "recovered" and derived == "recovered" else "not_recovered"
    return {"criteria": criteria, "observed": dict(observed), "expected_status": expected, "derived_status": derived, "status": status}


def _derive_status(observed: Mapping[str, Any]) -> str:
    pool_wait = _float(observed.get("pool_wait_p95_ms"), 999999.0)
    five_xx = _float(observed.get("five_xx_rate"), 1.0)
    provider_timeout = _float(observed.get("provider_timeout_rate"), 1.0)
    checkout_error = _float(observed.get("checkout_error_rate"), 1.0)
    if pool_wait <= 500 and five_xx <= 0.01:
        return "recovered"
    if provider_timeout <= 0.02 and checkout_error <= 0.01:
        return "recovered"
    return "not_recovered"


def _rollback_or_escalation(status: str, precheck: Mapping[str, Any]) -> dict[str, str]:
    if status == "recovered":
        return {"route": "monitor", "reason": "post-check met recovery criteria", "next_step": "continue read-only observation"}
    return {
        "route": "escalate",
        "reason": "post-check did not prove recovery",
        "next_step": str(precheck.get("rollback_plan", "escalate to incident commander")),
    }


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
