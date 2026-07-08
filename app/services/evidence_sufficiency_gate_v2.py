"""P76 evidence sufficiency gate v2.

P76 extends the P45 evidence-grounded judgment contract with a stricter
sufficiency gate. The gate decides whether a judgment has enough evidence for a
read-only conclusion, is ready for approval, requires a human, or must be
blocked as unsafe. It scores only offline fixture evidence and never executes
actions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from app.services.evidence_grounded_judgment import build_evidence_grounded_judgment_report
from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "offline_fixture_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}

_STRENGTH_SCORE = {"low": 0.08, "medium": 0.16, "high": 0.23}
_SAFE_DECISIONS = {"approval_ready", "sufficient_read_only"}


@dataclass(frozen=True)
class EvidenceSufficiencyGateV2Report:
    cases: tuple[dict[str, Any], ...]

    @classmethod
    def from_judgments(cls, judgments: Sequence[Mapping[str, Any]]) -> Self:
        return cls(tuple(_score_judgment(judgment) for judgment in judgments))

    def to_dict(self) -> dict[str, Any]:
        case_count = len(self.cases)
        sufficient = sum(1 for case in self.cases if case["gate_decision"] in _SAFE_DECISIONS)
        approval_ready = sum(1 for case in self.cases if case["gate_decision"] == "approval_ready")
        human_required = sum(1 for case in self.cases if case["gate_decision"] == "human_required")
        unsafe_auto = sum(1 for case in self.cases if case["auto_execute_allowed"])
        missing_count = sum(int(case["missing_evidence_count"]) for case in self.cases)
        scores = [float(case["sufficiency_score"]) for case in self.cases]
        payload = {
            "summary": {
                "case_count": case_count,
                "sufficient_read_only_count": sufficient,
                "approval_ready_count": approval_ready,
                "human_required_count": human_required,
                "unsafe_auto_execute_count": unsafe_auto,
                "blocked_unsafe_auto_execute_count": sum(
                    1 for case in self.cases if case["gate_decision"] == "blocked_unsafe_auto_execute"
                ),
                "passed": case_count > 0 and unsafe_auto == 0 and sufficient + human_required == case_count,
            },
            "score": {
                "mean_sufficiency_score": _mean(scores),
                "minimum_sufficiency_score": round(min(scores), 3) if scores else 0.0,
                "maximum_sufficiency_score": round(max(scores), 3) if scores else 0.0,
                "missing_evidence_item_count": missing_count,
                "evidence_source_count": len({source for case in self.cases for source in case["evidence_sources"]}),
            },
            "boundary": dict(_BOUNDARY),
            "cases": list(self.cases),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_evidence_sufficiency_gate_v2_report(cases_path: str | Path) -> EvidenceSufficiencyGateV2Report:
    p45_payload = build_evidence_grounded_judgment_report(cases_path).to_dict()
    judgments = tuple(row for row in _sequence(p45_payload.get("judgments", ())) if isinstance(row, Mapping))
    return EvidenceSufficiencyGateV2Report.from_judgments(judgments)


def render_evidence_sufficiency_gate_v2_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Evidence Sufficiency Gate v2",
        "",
        "P76 scores whether each evidence-grounded judgment is sufficient for read-only conclusion, approval, or human escalation.",
        "",
        "## Summary",
        "",
        f"- Case count: {summary.get('case_count', 0)}",
        f"- Sufficient read-only: {summary.get('sufficient_read_only_count', 0)}",
        f"- Approval-ready: {summary.get('approval_ready_count', 0)}",
        f"- Human-required: {summary.get('human_required_count', 0)}",
        f"- Unsafe auto-execute: {summary.get('unsafe_auto_execute_count', 0)}",
        f"- Mean sufficiency score: {score.get('mean_sufficiency_score', 0.0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Gate decisions",
        "",
    ]
    for case in _sequence(payload.get("cases", ())):
        if isinstance(case, Mapping):
            lines.append(
                f"- `{case.get('case_id')}` decision={case.get('gate_decision')} "
                f"score={case.get('sufficiency_score')} reasons={', '.join(str(item) for item in _sequence(case.get('reasons', ())))}"
            )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Offline fixture scoring only.",
            "- No live APIs, credentials, network calls, production mutation, remediation execution, or action execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_evidence_sufficiency_gate_v2_outputs(
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
        output_md_path.write_text(render_evidence_sufficiency_gate_v2_markdown(payload), encoding="utf-8")


def _score_judgment(judgment: Mapping[str, Any]) -> dict[str, Any]:
    supporting = tuple(item for item in _sequence(judgment.get("supporting_evidence", ())) if isinstance(item, Mapping))
    counter = tuple(item for item in _sequence(judgment.get("counter_evidence", ())) if isinstance(item, Mapping))
    missing = tuple(str(item) for item in _sequence(judgment.get("missing_evidence", ())))
    boundary = _mapping(judgment.get("action_boundary"))
    contract = _mapping(judgment.get("contract"))
    sources = tuple(sorted({str(item.get("source", "unknown")) for item in supporting + counter}))
    confidence = _float(judgment.get("confidence"), 0.0)
    raw_score = (
        0.17
        + min(0.62, sum(_STRENGTH_SCORE.get(str(item.get("strength", "low")), 0.08) for item in supporting))
        + min(0.27, len({str(item.get("source", "unknown")) for item in supporting}) * 0.09)
        + min(0.10, len(counter) * 0.05)
        + confidence * 0.22
        - len(missing) * 0.08
        - (0.20 if contract.get("valid") is False else 0.0)
    )
    sufficiency_score = round(max(0.0, min(1.0, raw_score)), 3)
    auto_execute_allowed = boundary.get("auto_execute_allowed") is True
    gate_decision, reasons = _decision(
        sufficiency_score=sufficiency_score,
        support_count=len(supporting),
        missing_count=len(missing),
        route=str(boundary.get("route", "human_required")),
        auto_execute_allowed=auto_execute_allowed,
        contract_valid=contract.get("valid") is True,
    )
    return {
        "case_id": str(judgment.get("case_id", "unknown")),
        "claim": str(judgment.get("claim", "unknown")),
        "sufficiency_score": sufficiency_score,
        "gate_decision": gate_decision,
        "reasons": reasons,
        "required_next_evidence": list(missing),
        "evidence_sources": list(sources),
        "supporting_evidence_count": len(supporting),
        "counter_evidence_count": len(counter),
        "missing_evidence_count": len(missing),
        "confidence": confidence,
        "auto_execute_allowed": auto_execute_allowed,
        "contract_valid": contract.get("valid") is True,
    }


def _decision(
    *,
    sufficiency_score: float,
    support_count: int,
    missing_count: int,
    route: str,
    auto_execute_allowed: bool,
    contract_valid: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if auto_execute_allowed:
        return "blocked_unsafe_auto_execute", ["unsafe auto-execute requested"]
    if not contract_valid:
        reasons.append("invalid P45 evidence contract")
    if sufficiency_score < 0.60 or support_count < 2:
        reasons.append("insufficient supporting strength")
    if missing_count >= 3:
        reasons.append("too much missing evidence")
    if reasons:
        return "human_required", reasons
    if route == "approval_required" or missing_count:
        return "approval_ready", ["enough evidence for approval-gated operator decision"]
    return "sufficient_read_only", ["enough evidence for read-only judgment"]


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
    "EvidenceSufficiencyGateV2Report",
    "build_evidence_sufficiency_gate_v2_report",
    "render_evidence_sufficiency_gate_v2_markdown",
    "write_evidence_sufficiency_gate_v2_outputs",
]
