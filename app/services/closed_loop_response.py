"""Closed-loop local/mock incident response agent.

P20 connects judgment, missing-evidence collection, revised judgment, action
proposal, simulation, and final routing into one auditable loop. It never
executes proposed remediation actions.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.action import ActionRequest
from app.services.action_simulator import ActionSimulator
from app.services.judgment_dataset import JudgmentCase
from app.services.llm_judgment import LLMJudgmentProvider, MockLLMJudgmentProvider
from app.services.model_quality_lab import ModelQualityCaseResult, evaluate_model_quality_case
from app.services.operator_improvement_loop import build_improvement_plan
from app.services.redaction import redact_text, redact_value

_READ_ONLY_EVIDENCE_TOOLS = {
    "mock.search_logs": "Fetched sanitized matching log lines from local/mock evidence cache.",
    "mock.query_metrics": "Fetched sanitized metric window and baseline from local/mock evidence cache.",
    "mock.fetch_trace_context": "Fetched sanitized trace/span context from local/mock evidence cache.",
    "mock.get_service_health": "Fetched sanitized service health from local/mock evidence cache.",
    "mock.get_recent_deploys": "Fetched sanitized recent deploy metadata from local/mock evidence cache.",
    "mock.get_error_context": "Fetched sanitized error context from local/mock evidence cache.",
}
_BLOCKED_TOOL_MARKERS = ("restart", "rollback", "shell", "database", "db_", "cloud", "kubernetes", "kubectl", "terraform", "aws", "gcloud")


@dataclass(frozen=True)
class TraceStep:
    step: str
    summary: str
    data: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "summary": self.summary, "data": dict(redact_value(dict(self.data)))}


@dataclass(frozen=True)
class ClosedLoopResult:
    case_id: str
    provider: str
    model: str
    initial_judgment: Mapping[str, Any]
    revised_judgment: Mapping[str, Any]
    fetched_evidence: tuple[Mapping[str, Any], ...]
    proposed_actions: tuple[Mapping[str, Any], ...]
    simulations: tuple[Mapping[str, Any], ...]
    final_decision: Mapping[str, Any]
    trace: tuple[TraceStep, ...]
    score_delta: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "provider": self.provider,
            "model": self.model,
            "initial_judgment": dict(redact_value(dict(self.initial_judgment))),
            "revised_judgment": dict(redact_value(dict(self.revised_judgment))),
            "score_delta": dict(self.score_delta),
            "fetched_evidence": [dict(redact_value(dict(item))) for item in self.fetched_evidence],
            "proposed_actions": [dict(redact_value(dict(item))) for item in self.proposed_actions],
            "simulations": [dict(redact_value(dict(item))) for item in self.simulations],
            "final_decision": dict(redact_value(dict(self.final_decision))),
            "trace": [step.to_dict() for step in self.trace],
            "executed_actions": [],
            "boundary": {
                "local_mock_only": True,
                "action_execution_enabled": False,
                "production_mutation_enabled": False,
                "default_external_model_calls": False,
            },
        }


def run_closed_loop_response(
    case: JudgmentCase,
    *,
    provider: LLMJudgmentProvider | None = None,
    max_evidence: int = 20,
) -> ClosedLoopResult:
    selected_provider = provider or MockLLMJudgmentProvider()
    initial = evaluate_model_quality_case(case, provider=selected_provider, max_evidence=max_evidence)
    initial_payload = initial.to_dict()
    improvement_plan = build_improvement_plan(_single_case_report(initial))
    missing_tools = _tools_from_improvement_plan(improvement_plan.to_dict())
    fetched_evidence = tuple(
        execute_read_only_evidence_plan(case_id=case.id, tools=missing_tools, reason="closed-loop evidence gap follow-up")
    )
    revised_case = _case_with_fetched_evidence(case, fetched_evidence)
    revised = evaluate_model_quality_case(revised_case, provider=selected_provider, max_evidence=max_evidence + len(fetched_evidence))
    revised_payload = revised.to_dict()
    proposed_actions = tuple(_propose_actions(revised_case, revised_payload))
    simulations = tuple(_simulate_action(action) for action in proposed_actions)
    final_decision = _final_decision(revised_payload, simulations, fetched_evidence)
    trace = (
        TraceStep("observe", f"Observed case {case.id}", {"case_title": case.title, "evidence_count": len(case.evidence)}),
        TraceStep("initial_judgment", "Ran initial LLM-shaped judgment", _judgment_trace_payload(initial_payload)),
        TraceStep(
            "evidence_gap",
            "Derived missing-evidence plan from initial failures",
            {"tools": list(missing_tools), "candidate_count": len(improvement_plan.top_candidates)},
        ),
        TraceStep("evidence_fetch", "Fetched read-only local/mock evidence", {"fetched_count": len(fetched_evidence), "evidence_ids": [item["id"] for item in fetched_evidence]}),
        TraceStep("revised_judgment", "Rebuilt context and ran revised judgment", _judgment_trace_payload(revised_payload)),
        TraceStep("action_proposal", "Proposed bounded local/mock actions only", {"action_count": len(proposed_actions), "actions": [item["action_type"] for item in proposed_actions]}),
        TraceStep("simulation", "Dry-ran proposed actions without execution", {"simulation_count": len(simulations), "statuses": [item["status"] for item in simulations]}),
        TraceStep("final_decision", "Selected final route from revised judgment and simulations", final_decision),
    )
    return ClosedLoopResult(
        case_id=case.id,
        provider=str(revised_payload.get("provider", initial_payload.get("provider", "unknown"))),
        model=str(revised_payload.get("model", initial_payload.get("model", "unknown"))),
        initial_judgment=initial_payload,
        revised_judgment=revised_payload,
        fetched_evidence=fetched_evidence,
        proposed_actions=proposed_actions,
        simulations=simulations,
        final_decision=final_decision,
        trace=trace,
        score_delta={
            "raw_provider_score_delta": round(float(revised.raw_provider_score) - float(initial.raw_provider_score), 3),
            "calibrated_score_delta": round(float(revised.calibrated_score) - float(initial.calibrated_score), 3),
        },
    )


def execute_read_only_evidence_plan(*, case_id: str, tools: Sequence[str], reason: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for tool in tools:
        normalized = str(tool)
        lowered = normalized.lower()
        if normalized not in _READ_ONLY_EVIDENCE_TOOLS or any(marker in lowered for marker in _BLOCKED_TOOL_MARKERS):
            continue
        evidence.append(
            {
                "id": f"fetched:{normalized}",
                "type": "diagnostic",
                "source": "closed_loop",
                "content": redact_text(f"{_READ_ONLY_EVIDENCE_TOOLS[normalized]} Reason: {reason} Case: {case_id}."),
                "metadata": {
                    "tool": normalized,
                    "read_only": True,
                    "local_mock_only": True,
                    "action_execution_enabled": False,
                },
            }
        )
    return evidence


def render_closed_loop_markdown(result: ClosedLoopResult) -> str:
    payload = result.to_dict()
    lines = [
        "# OpsCat Closed-loop Incident Response",
        "",
        "Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; does not claim unattended production operation.",
        "",
        f"- Case: `{payload['case_id']}`",
        f"- Provider: {payload['provider']}",
        f"- Model: {payload['model']}",
        f"- Initial route: {payload['initial_judgment'].get('final_route')}",
        f"- Revised route: {payload['revised_judgment'].get('final_route')}",
        f"- Final decision: {payload['final_decision'].get('route')}",
        f"- Fetched evidence: {len(payload['fetched_evidence'])}",
        f"- Proposed actions: {len(payload['proposed_actions'])}",
        "",
        "## Closed-loop trace",
    ]
    for step in payload["trace"]:
        lines.append(f"- `{step['step']}`: {redact_text(step['summary'])}")
    lines.extend(["", "## Simulations"])
    if payload["simulations"]:
        for simulation in payload["simulations"]:
            lines.append(f"- `{simulation['action_type']}` status={simulation['status']} ok={simulation.get('ok')}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_closed_loop_outputs(
    result: ClosedLoopResult,
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_closed_loop_markdown(result), encoding="utf-8")


def _single_case_report(result: ModelQualityCaseResult) -> dict[str, Any]:
    row = result.to_dict()
    counts = Counter(row.get("failure_taxonomy", []))
    return {
        "provider": row.get("provider", "unknown"),
        "model": row.get("model", "unknown"),
        "case_count": 1,
        "raw_provider_score": row.get("raw_provider_score", 0.0),
        "calibrated_score": row.get("calibrated_score", 0.0),
        "calibration_delta": row.get("calibration_delta", 0.0),
        "calibration_wins": 1 if row.get("calibration_win") else 0,
        "failure_taxonomy_counts": dict(counts),
        "results": [row],
    }


def _tools_from_improvement_plan(plan: Mapping[str, Any]) -> tuple[str, ...]:
    tools: list[str] = []
    plans = plan.get("missing_evidence_plans", [])
    if isinstance(plans, Sequence) and not isinstance(plans, (str, bytes, bytearray)):
        for item in plans:
            if isinstance(item, Mapping):
                raw_tools = item.get("read_only_tools", [])
                if isinstance(raw_tools, Sequence) and not isinstance(raw_tools, (str, bytes, bytearray)):
                    tools.extend(str(tool) for tool in raw_tools)
    if not tools:
        tools.extend(("mock.search_logs", "mock.query_metrics", "mock.get_service_health"))
    return tuple(dict.fromkeys(tools))


def _case_with_fetched_evidence(case: JudgmentCase, fetched: Sequence[Mapping[str, Any]]) -> JudgmentCase:
    return JudgmentCase(
        id=case.id,
        title=case.title,
        incident=case.incident,
        evidence=[*case.evidence, *[dict(item) for item in fetched]],
        rubric=case.rubric,
        source=case.source,
        signals=case.signals,
        tags=case.tags,
        local_mock_only=True,
    )


def _propose_actions(case: JudgmentCase, judgment_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    final_route = str(judgment_payload.get("final_route", "human_required"))
    service = str(case.incident.get("service") or "unknown-service")
    environment = str(case.incident.get("environment") or "local")
    evidence_ids = [str(item.get("id")) for item in case.evidence if item.get("id")]
    if final_route == "blocked":
        return []
    if final_route == "local_mock_auto_allowed":
        return [
            {
                "action_type": "timeline.add_note",
                "target": service,
                "environment": environment,
                "payload": {"note": "Closed-loop diagnostic note only", "evidence_ids": evidence_ids},
                "requires_approval": False,
            }
        ]
    if final_route == "approval_required":
        return [
            {
                "action_type": "mock.create_incident_ticket",
                "target": service,
                "environment": environment,
                "payload": {"title": f"OpsCat approval required for {case.id}", "evidence_ids": evidence_ids},
                "requires_approval": True,
            }
        ]
    return [
        {
            "action_type": "report.generate",
            "target": service,
            "environment": environment,
            "payload": {"title": f"OpsCat human review for {case.id}", "evidence_ids": evidence_ids},
            "requires_approval": False,
        }
    ]


def _simulate_action(action: Mapping[str, Any]) -> dict[str, Any]:
    request = ActionRequest(
        action_type=str(action.get("action_type", "unknown")),
        target=str(action.get("target", "unknown")),
        environment=str(action.get("environment", "local")),
        payload=action.get("payload", {}) if isinstance(action.get("payload", {}), Mapping) else {},
        approved=False,
    )
    return ActionSimulator().simulate(request).to_dict()


def _final_decision(revised_payload: Mapping[str, Any], simulations: Sequence[Mapping[str, Any]], fetched_evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    route = str(revised_payload.get("final_route", "human_required"))
    if any(str(item.get("status")) in {"blocked", "escalate"} for item in simulations):
        route = "human_required" if route != "blocked" else "blocked"
    if not fetched_evidence and route == "local_mock_auto_allowed":
        route = "human_required"
    return {
        "route": route,
        "reason": "closed-loop revised judgment plus simulation; no action execution",
        "action_execution_enabled": False,
        "requires_human": route in {"human_required", "blocked"},
    }


def _judgment_trace_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider_route": payload.get("provider_route"),
        "final_route": payload.get("final_route"),
        "raw_provider_score": payload.get("raw_provider_score"),
        "calibrated_score": payload.get("calibrated_score"),
        "failure_taxonomy": payload.get("failure_taxonomy", []),
    }
