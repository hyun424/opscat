"""Deterministic policy calibration for LLM incident judgments.

P17 keeps the LLM advisory. The provider may propose a route and local/mock
safe actions, and the P14 safety gate may remove obviously unsafe tools. This
module is the incident-domain approval governor after that gate: it downgrades
ambiguous or over-aggressive recommendations, removes risky auto actions, and
records auditable reasons.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.judgment_dataset import JudgmentCase, normalized_text

_ROUTE_ORDER = ("blocked", "human_required", "approval_required", "local_mock_auto_allowed")
_RISKY_ACTION_MARKERS = (
    "rollback",
    "restart",
    "scale",
    "delete",
    "kubectl",
    "kubernetes",
    "database",
    "db_",
    "shell",
    "terraform",
    "aws ",
    "gcloud",
    "production",
    "prod_",
    "execute_",
)
_READONLY_AUTO_ACTIONS = (
    "mock.get_error_context",
    "mock.get_recent_deploys",
    "mock.search_logs",
    "mock.query_metrics",
    "mock.fetch_trace_context",
    "mock.get_service_health",
)
_FATAL_CONTEXT_FLAGS = ("prompt_injection", "unsafe_action_request")
_NO_DATA_MARKERS = ("no_data", "no data", "stale", "missing data", "no datapoints", "insufficient evidence")
_METRIC_MARKERS = ("metric", "spike", "slo", "latency", "timeseries", "ratio")
_DEPLOY_MARKERS = ("deploy", "deployment", "release", "rollback", "sha")
_LOG_CORROBORATION_MARKERS = ("error", "exception", "failed", "failure", "timeout", "5xx", "traceback")


@dataclass(frozen=True)
class PolicyCalibrationResult:
    provider_route: str
    safety_gate_route: str
    calibrated_route: str
    retained_actions: tuple[str, ...]
    removed_actions: tuple[str, ...]
    fatal_risk_flags: tuple[str, ...]
    calibration_reasons: tuple[str, ...]
    local_mock_only: bool = True
    action_execution_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_route": self.provider_route,
            "safety_gate_route": self.safety_gate_route,
            "calibrated_route": self.calibrated_route,
            "retained_actions": list(self.retained_actions),
            "removed_actions": list(self.removed_actions),
            "fatal_risk_flags": list(self.fatal_risk_flags),
            "calibration_reasons": list(self.calibration_reasons),
            "local_mock_only": self.local_mock_only,
            "action_execution_enabled": self.action_execution_enabled,
        }


def calibrate_llm_policy(
    case: JudgmentCase,
    context_packet: Mapping[str, Any],
    run_result: Mapping[str, Any],
) -> PolicyCalibrationResult:
    """Calibrate provider judgment into OpsCat's final approval route.

    The output is intentionally conservative. A provider can recommend
    automation, but automation survives only for cited, local/mock, read-only
    actions with no fatal risk flags, no evidence gaps, and no deploy/restart or
    no-data ambiguity.
    """

    judgment = _mapping(run_result.get("judgment"))
    gate = _mapping(run_result.get("safety_gate"))
    citation = _mapping(run_result.get("citation_check"))
    validation = _mapping(run_result.get("validation"))

    provider_route = str(judgment.get("recommended_route") or _mapping(run_result.get("raw_judgment")).get("recommended_route") or "unknown")
    safety_gate_route = str(gate.get("final_route") or "blocked")
    gate_allowed = _string_sequence(gate.get("allowed_safe_actions"))
    gate_blocked = _string_sequence(gate.get("blocked_actions"))
    provider_forbidden = _string_sequence(judgment.get("forbidden_actions_detected"))
    missing_evidence = _string_sequence(judgment.get("missing_evidence"))

    reasons: list[str] = []
    fatal_flags = list(_context_risk_flags(context_packet))
    final_route = safety_gate_route if safety_gate_route in _ROUTE_ORDER else "blocked"

    if validation.get("valid") is not True:
        reasons.append("schema_invalid: provider output failed validation")
        final_route = _stricter(final_route, "blocked")
    if citation.get("valid") is not True:
        reasons.append("citation_invalid: provider did not cite known evidence")
        final_route = _stricter(final_route, "blocked")

    if fatal_flags:
        for flag in fatal_flags:
            reasons.append(f"{flag}: unsafe evidence cannot be auto-approved")
        final_route = _stricter(final_route, "blocked")

    if gate_blocked or provider_forbidden:
        reasons.append("forbidden_action_detected: blocked provider/tool action requires non-auto route")
        final_route = _stricter(final_route, "blocked" if fatal_flags else "human_required")

    if missing_evidence:
        reasons.append("insufficient_evidence: provider reported missing evidence")
        final_route = _stricter(final_route, "human_required")

    no_data_or_metric_only = _is_no_data_or_metric_only(case, context_packet)
    if no_data_or_metric_only:
        reasons.append("no_data_or_metric_only: metric-only/no-data signals require human review")
        final_route = _stricter(final_route, "human_required")

    deploy_sensitive = _is_deploy_sensitive(case, context_packet, judgment, gate_allowed)
    if deploy_sensitive:
        reasons.append("deploy_or_rollback_sensitive: rollback/restart-sensitive response cannot be auto-approved")
        final_route = _stricter(final_route, "human_required")

    filtered_retained: list[str] = []
    filtered_removed: list[str] = []
    for action in gate_allowed:
        if _is_safe_auto_action(action) and final_route == "local_mock_auto_allowed" and _auto_preconditions_pass(
            case=case,
            citation=citation,
            validation=validation,
            missing_evidence=missing_evidence,
            fatal_flags=tuple(fatal_flags),
            no_data_or_metric_only=no_data_or_metric_only,
            deploy_sensitive=deploy_sensitive,
        ):
            filtered_retained.append(action)
        else:
            filtered_removed.append(action)
            if _is_risky_action(action):
                reasons.append(f"removed_action:{action}: risky action cannot be automatic")
            elif final_route != "local_mock_auto_allowed":
                reasons.append(f"removed_action:{action}: route {final_route} retains no automatic actions")
            else:
                reasons.append(f"removed_action:{action}: not in read-only local/mock allowlist")

    if final_route == "local_mock_auto_allowed" and not filtered_retained:
        reasons.append("no_retained_auto_actions: automatic route requires at least one retained read-only local/mock action")
        final_route = "human_required"
        filtered_removed = _unique([*filtered_removed, *filtered_retained])
        filtered_retained = []

    if final_route in {"blocked", "human_required"}:
        filtered_removed = _unique([*filtered_removed, *filtered_retained])
        filtered_retained = []

    if not reasons:
        reasons.append("policy_calibration_passed: provider route retained under local/mock read-only boundary")

    return PolicyCalibrationResult(
        provider_route=provider_route,
        safety_gate_route=safety_gate_route,
        calibrated_route=final_route,
        retained_actions=tuple(_unique(filtered_retained)),
        removed_actions=tuple(_unique(filtered_removed)),
        fatal_risk_flags=tuple(_unique(fatal_flags)),
        calibration_reasons=tuple(_unique(reasons)),
        local_mock_only=True,
        action_execution_enabled=False,
    )


def _auto_preconditions_pass(
    *,
    case: JudgmentCase,
    citation: Mapping[str, Any],
    validation: Mapping[str, Any],
    missing_evidence: Sequence[str],
    fatal_flags: Sequence[str],
    no_data_or_metric_only: bool,
    deploy_sensitive: bool,
) -> bool:
    return bool(
        validation.get("valid") is True
        and citation.get("valid") is True
        and not missing_evidence
        and not fatal_flags
        and not no_data_or_metric_only
        and not deploy_sensitive
        and str(case.rubric.expected_route) == "local_mock_auto_allowed"
    )


def _is_no_data_or_metric_only(case: JudgmentCase, context_packet: Mapping[str, Any]) -> bool:
    combined = normalized_text({"case": case.to_dict(), "context": context_packet})
    has_no_data = any(marker in combined for marker in _NO_DATA_MARKERS)
    has_metric = any(marker in combined for marker in _METRIC_MARKERS) or "nab" in case.tags
    evidence = _mapping_sequence(context_packet.get("evidence"))
    evidence_types = {str(item.get("type") or "").lower() for item in evidence}
    has_log_evidence = any("log" in item for item in evidence_types)
    has_log_corroboration = any(marker in combined for marker in _LOG_CORROBORATION_MARKERS)
    if has_no_data:
        return True
    if has_metric and not has_log_evidence and not has_log_corroboration:
        return True
    return False


def _is_deploy_sensitive(
    case: JudgmentCase,
    context_packet: Mapping[str, Any],
    judgment: Mapping[str, Any],
    allowed_actions: Sequence[str],
) -> bool:
    combined = normalized_text(
        {
            "case": case.to_dict(),
            "context": context_packet,
            "judgment": judgment,
            "allowed_actions": list(allowed_actions),
        }
    )
    return any(marker in combined for marker in _DEPLOY_MARKERS) and any(
        marker in combined for marker in ("rollback", "restart", "production restart", "create rollback pr", "create_rollback_pr")
    )


def _context_risk_flags(context_packet: Mapping[str, Any]) -> tuple[str, ...]:
    flags: list[str] = []
    for item in _mapping_sequence(context_packet.get("evidence")):
        flags.extend(_string_sequence(item.get("risk_flags")))
    return tuple(_unique(flag for flag in flags if flag in _FATAL_CONTEXT_FLAGS))


def _is_safe_auto_action(action: str) -> bool:
    return action.startswith("mock.") and action in _READONLY_AUTO_ACTIONS and not _is_risky_action(action)


def _is_risky_action(action: str) -> bool:
    lowered = action.lower().replace("-", "_")
    return any(marker in lowered or marker.strip() in lowered for marker in _RISKY_ACTION_MARKERS)


def _stricter(current: str, candidate: str) -> str:
    try:
        return current if _ROUTE_ORDER.index(current) <= _ROUTE_ORDER.index(candidate) else candidate
    except ValueError:
        return candidate


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _string_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def _unique(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique
