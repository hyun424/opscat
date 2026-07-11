"""P45 evidence-grounded judgment contract."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "offline_fixture_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_STRENGTH_WEIGHT = {"low": 0.18, "medium": 0.28, "high": 0.38}


@dataclass(frozen=True)
class EvidenceGroundedJudgmentReport:
    judgments: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        case_count = len(self.judgments)
        valid_count = sum(1 for row in self.judgments if row["contract"]["valid"])
        conservative_count = sum(1 for row in self.judgments if row["action_boundary"]["approval_required"] or row["action_boundary"]["route"] == "human_required")
        unsafe_auto = sum(1 for row in self.judgments if row["action_boundary"]["auto_execute_allowed"])
        payload = {
            "summary": {
                "case_count": case_count,
                "valid_contract_count": valid_count,
                "grounded_ratio": _ratio(valid_count, case_count),
                "conservative_route_count": conservative_count,
                "conservative_route_ratio": _ratio(conservative_count, case_count),
                "unsafe_auto_execute_count": unsafe_auto,
                "passed": case_count > 0 and valid_count == case_count and unsafe_auto == 0,
            },
            "boundary": dict(_BOUNDARY),
            "judgments": list(self.judgments),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_evidence_grounded_judgment_report(cases_path: str | Path) -> EvidenceGroundedJudgmentReport:
    cases = _load_cases(cases_path)
    return EvidenceGroundedJudgmentReport(tuple(_build_judgment(case) for case in cases))


def validate_judgment_contract(judgment: Mapping[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    supporting = _sequence(judgment.get("supporting_evidence", ()))
    counter = _sequence(judgment.get("counter_evidence", ()))
    missing = _sequence(judgment.get("missing_evidence", ()))
    confidence = _float(judgment.get("confidence"), -1.0)
    boundary = _mapping(judgment.get("action_boundary"))
    if not judgment.get("claim"):
        violations.append("missing_claim")
    if not supporting:
        violations.append("missing_supporting_evidence")
    if not counter:
        violations.append("missing_counter_evidence")
    if confidence < 0.0 or confidence > 1.0:
        violations.append("invalid_confidence")
    if confidence > 0.95:
        violations.append("overconfident_claim")
    if missing and boundary.get("auto_execute_allowed") is True:
        violations.append("auto_execute_with_missing_evidence")
    if boundary.get("auto_execute_allowed") is True and boundary.get("approval_required") is not True:
        violations.append("unsafe_auto_execute_without_approval")
    if not _sequence(boundary.get("blocked_actions", ())):
        violations.append("missing_blocked_actions")
    if not _sequence(boundary.get("safe_actions", ())):
        violations.append("missing_safe_actions")
    return {"valid": not violations, "violations": violations}


def render_evidence_grounded_judgment_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Evidence-Grounded Judgment Contract",
        "",
        "Every judgment must carry support, counter-evidence, missing evidence, confidence, uncertainty, and an action boundary.",
        "",
        "## Summary",
        f"- Case count: {summary.get('case_count')}",
        f"- Valid contracts: {summary.get('valid_contract_count')}",
        f"- Grounded ratio: {summary.get('grounded_ratio')}",
        f"- Conservative routes: {summary.get('conservative_route_count')}",
        f"- Unsafe auto-execute: {summary.get('unsafe_auto_execute_count')}",
        "",
        "## Judgments",
    ]
    for row in _sequence(payload.get("judgments", ())):
        if isinstance(row, Mapping):
            boundary = _mapping(row.get("action_boundary"))
            lines.append(f"- `{row.get('case_id')}` claim={row.get('claim')} confidence={row.get('confidence')} route={boundary.get('route')}")
    lines.extend(["", "## Action boundary", "- Production mutation and remediation execution remain disabled by default."])
    return "\n".join(lines) + "\n"


def write_evidence_grounded_judgment_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_evidence_grounded_judgment_markdown(payload), encoding="utf-8")


def _load_cases(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P45 cases must be a mapping")
    return tuple(item for item in _sequence(data.get("cases", ())) if isinstance(item, Mapping))


def _build_judgment(case: Mapping[str, Any]) -> dict[str, Any]:
    supporting = tuple(_evidence_item(item) for item in _sequence(case.get("signals", ())) if isinstance(item, Mapping))
    counter = tuple(_evidence_item(item) for item in _sequence(case.get("counter_signals", ())) if isinstance(item, Mapping))
    missing = tuple(str(item) for item in _sequence(case.get("missing", ())))
    confidence = _confidence(supporting, counter, missing)
    route = _route(confidence, missing, str(case.get("expected_route", "human_required")))
    boundary = {
        "route": route,
        "auto_execute_allowed": False,
        "approval_required": route == "approval_required",
        "safe_actions": ["open incident note", "collect more read-only evidence", "draft remediation plan"],
        "blocked_actions": ["production rollback", "restart production", "delete data", "run unrestricted shell"],
    }
    judgment = {
        "case_id": str(case.get("id", "p45-case")),
        "claim": str(case.get("claim", "unknown")),
        "supporting_evidence": list(supporting),
        "counter_evidence": list(counter),
        "missing_evidence": list(missing),
        "supporting_evidence_count": len(supporting),
        "counter_evidence_count": len(counter),
        "missing_evidence_count": len(missing),
        "confidence": confidence,
        "uncertainty_reason": _uncertainty_reason(missing, counter),
        "action_boundary": boundary,
    }
    judgment["contract"] = validate_judgment_contract(judgment)
    redacted = redact_value(judgment)
    return dict(redacted) if isinstance(redacted, Mapping) else judgment


def _evidence_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": str(item.get("source", "unknown")),
        "signal": str(item.get("signal", "unknown")),
        "value": str(item.get("value", "")),
        "strength": str(item.get("strength", "low")),
    }


def _confidence(supporting: Sequence[Mapping[str, Any]], counter: Sequence[Mapping[str, Any]], missing: Sequence[str]) -> float:
    support_score = sum(_STRENGTH_WEIGHT.get(str(item.get("strength", "low")), 0.18) for item in supporting)
    counter_penalty = 0.06 * len(counter)
    missing_penalty = 0.08 * len(missing)
    return round(max(0.05, min(0.95, 0.35 + support_score - counter_penalty - missing_penalty)), 2)


def _route(confidence: float, missing: Sequence[str], expected_route: str) -> str:
    if confidence < 0.55 or len(missing) >= 3:
        return "human_required"
    if expected_route == "approval_required" or missing:
        return "approval_required"
    return "read_only_auto_allowed"


def _uncertainty_reason(missing: Sequence[str], counter: Sequence[Mapping[str, Any]]) -> str:
    if missing:
        return "Missing evidence: " + ", ".join(missing)
    if counter:
        return "Counter-evidence exists and must remain visible."
    return "Evidence is sufficient for read-only judgment only."


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


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
