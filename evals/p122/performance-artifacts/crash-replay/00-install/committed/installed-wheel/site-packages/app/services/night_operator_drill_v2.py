"""P50 local night-operator drill v2."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.evidence_grounded_judgment import build_evidence_grounded_judgment_report
from app.services.hypothesis_reranker import build_hypothesis_reranker_report
from app.services.investigator_loop import build_investigator_loop_report
from app.services.redaction import redact_value
from app.services.remediation_verification_loop import build_remediation_verification_loop_report
from app.services.tool_selection_planner import build_tool_selection_planner_report

_BOUNDARY = {
    "offline_fixture_only": True,
    "read_only_or_mock_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_DEFAULTS = {
    "judgments": Path("evals/investigator/p45_judgment_cases.json"),
    "investigations": Path("evals/investigator/p46_investigation_cases.json"),
    "tools": Path("evals/investigator/p47_tool_selection_cases.json"),
    "reranks": Path("evals/investigator/p48_rerank_cases.json"),
    "remediations": Path("evals/investigator/p49_remediation_verification_cases.json"),
}


@dataclass(frozen=True)
class NightOperatorDrillV2Report:
    drills: tuple[dict[str, Any], ...]
    component_summaries: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        drill_count = len(self.drills)
        evidence_pass = sum(1 for drill in self.drills if drill["gates"]["evidence_contract_passed"])
        investigations = sum(1 for drill in self.drills if drill["gates"]["investigation_complete"])
        tool_plans = sum(int(drill["gates"]["read_only_tool_plan_count"]) for drill in self.drills)
        remediations = sum(1 for drill in self.drills if drill["gates"]["remediation_verification_present"])
        production_execution = sum(1 for drill in self.drills if drill["safety"]["production_execution_attempted"])
        unsafe_auto = sum(1 for drill in self.drills if drill["safety"]["unsafe_auto_execute_allowed"])
        local_ready = drill_count > 0 and evidence_pass == drill_count and investigations == drill_count and tool_plans >= drill_count
        payload = {
            "summary": {
                "drill_count": drill_count,
                "evidence_contract_pass_count": evidence_pass,
                "investigation_complete_count": investigations,
                "read_only_tool_plan_count": tool_plans,
                "remediation_verification_count": remediations,
                "production_execution_count": production_execution,
                "unsafe_auto_execute_count": unsafe_auto,
                "passed": local_ready and remediations >= 1 and production_execution == 0 and unsafe_auto == 0,
            },
            "readiness": {
                "local_night_watch_ready": local_ready,
                "unattended_production_ready": False,
                "unattended_production_blockers": [
                    "auth/session controls deferred",
                    "live connector validation not enabled in this drill",
                    "production mutation and remediation execution disabled",
                    "human approval boundary still required for risky action",
                ],
            },
            "boundary": dict(_BOUNDARY),
            "component_summaries": self.component_summaries,
            "drills": list(self.drills),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_night_operator_drill_v2_report(drills_path: str | Path) -> NightOperatorDrillV2Report:
    drills = _load_drills(drills_path)
    components = _component_summaries()
    return NightOperatorDrillV2Report(tuple(_build_drill(drill, components) for drill in drills), components)


def render_night_operator_drill_v2_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    readiness = _mapping(payload.get("readiness"))
    lines = [
        "# OpsCat Night Operator Drill v2",
        "",
        "Chains evidence contract, investigation, read-only tool planning, re-ranking, and remediation verification in a local night-watch drill.",
        "",
        "## Summary",
        f"- Drills: {summary.get('drill_count')}",
        f"- Evidence contract pass: {summary.get('evidence_contract_pass_count')}",
        f"- Investigation complete: {summary.get('investigation_complete_count')}",
        f"- Read-only tool plans: {summary.get('read_only_tool_plan_count')}",
        f"- Remediation verifications: {summary.get('remediation_verification_count')}",
        f"- local_night_watch_ready={str(readiness.get('local_night_watch_ready')).lower()}",
        f"- unattended_production_ready={str(readiness.get('unattended_production_ready')).lower()}",
        "",
        "## Drills",
    ]
    for drill in _sequence(payload.get("drills", ())) :
        if isinstance(drill, Mapping):
            lines.append(f"- `{drill.get('drill_id')}` outcome={drill.get('outcome')}")
            for step in _sequence(drill.get("decision_trace", ())) :
                lines.append(f"  - {step}")
    lines.extend(["", "## Boundary", "- This is local night-watch readiness, not unattended production autopilot readiness."])
    return "\n".join(lines) + "\n"


def write_night_operator_drill_v2_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_night_operator_drill_v2_markdown(payload), encoding="utf-8")


def _load_drills(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P50 drills must be a mapping")
    return tuple(item for item in _sequence(data.get("drills", ())) if isinstance(item, Mapping))


def _component_summaries() -> dict[str, Any]:
    return {
        "evidence": build_evidence_grounded_judgment_report(_DEFAULTS["judgments"]).to_dict()["summary"],
        "investigation": build_investigator_loop_report(_DEFAULTS["investigations"]).to_dict()["summary"],
        "tools": build_tool_selection_planner_report(_DEFAULTS["tools"]).to_dict()["summary"],
        "rerank": build_hypothesis_reranker_report(_DEFAULTS["reranks"]).to_dict()["summary"],
        "remediation": build_remediation_verification_loop_report(_DEFAULTS["remediations"]).to_dict()["summary"],
    }


def _build_drill(drill: Mapping[str, Any], components: Mapping[str, Any]) -> dict[str, Any]:
    tool_summary = _mapping(components.get("tools"))
    remediation_summary = _mapping(components.get("remediation"))
    rerank_summary = _mapping(components.get("rerank"))
    read_only_tool_count = max(1, int(tool_summary.get("selected_tool_count", 0)) // 2)
    remediation_present = int(remediation_summary.get("recovery_verified_count", 0)) + int(
        remediation_summary.get("failed_verification_escalation_count", 0)
    ) >= 1
    anti_anchoring = int(rerank_summary.get("anti_anchoring_demotions", 0)) >= 1
    gates = {
        "evidence_contract_passed": bool(_mapping(components.get("evidence")).get("passed")),
        "investigation_complete": bool(_mapping(components.get("investigation")).get("passed")),
        "read_only_tool_plan_count": read_only_tool_count,
        "rerank_or_anti_anchoring_present": anti_anchoring,
        "remediation_verification_present": remediation_present,
    }
    safety = {"production_execution_attempted": False, "unsafe_auto_execute_allowed": False, "live_api_called": False}
    return {
        "drill_id": str(drill.get("id", "p50-drill")),
        "refs": {
            "judgment": str(drill.get("judgment_ref", "")),
            "incident": str(drill.get("incident_ref", "")),
            "tool_plan": str(drill.get("tool_plan_ref", "")),
            "rerank": str(drill.get("rerank_ref", "")),
            "remediation": str(drill.get("remediation_ref", "")),
        },
        "gates": gates,
        "safety": safety,
        "outcome": "local_watch_ready" if all(gates.values()) and not any(safety.values()) else "needs_review",
        "decision_trace": [
            "observe and validate evidence-grounded judgment contract",
            "generate and verify investigation hypothesis state",
            "select read-only tools and block mutation/shell/remediation execution",
            "re-rank hypotheses after investigation evidence to reduce anchoring",
            "verify mock/draft remediation outcome or escalate when not recovered",
        ],
    }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
