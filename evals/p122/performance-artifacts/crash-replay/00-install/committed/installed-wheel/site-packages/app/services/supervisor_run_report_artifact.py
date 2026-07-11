"""P87 supervisor run report artifact.

Builds a structured local/mock JSON and Markdown report from P86-style
resumable supervisor run state. This module is a reporting layer only: it does
not execute actions, commands, subprocesses, agents, API calls, credential
reads, network calls, remediation, or production mutations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value
from app.services.resumable_local_supervisor_runner import (
    ResumableSupervisorScenario,
    ResumableSupervisorStopReason,
    evaluate_resumable_local_supervisor_fixture,
)

_CLAIM_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "report_artifact_only": True,
    "consumes_p86_run_state": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "process_spawn_enabled": False,
    "agent_spawn_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}

_ZERO_SIDE_EFFECT_COUNTERS: dict[str, int] = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "shell_execution_count": 0,
    "process_spawn_count": 0,
    "agent_spawn_count": 0,
}

_TERMINAL_REASONS = {
    ResumableSupervisorStopReason.COMPLETED_ALL.value,
    ResumableSupervisorStopReason.NEEDS_HUMAN.value,
    ResumableSupervisorStopReason.FAILED_GUARDRAIL.value,
    ResumableSupervisorStopReason.NO_SAFE_WORK.value,
}


@dataclass(frozen=True)
class SupervisorRunReportArtifact:
    suite: Mapping[str, Any]
    scenarios: tuple[ResumableSupervisorScenario, ...]
    reports: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_fixture(cls, path: str | Path) -> Self:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        scenarios = tuple(
            ResumableSupervisorScenario.from_dict(item)
            for item in _sequence(data.get("scenarios", ()))
            if isinstance(item, Mapping)
        )
        p86_report = evaluate_resumable_local_supervisor_fixture(path)
        p86_runs = p86_report.to_dict()["runs"]
        return cls(
            suite=_mapping(data.get("suite")),
            scenarios=scenarios,
            reports=tuple(_build_report(run, scenario) for run, scenario in zip(p86_runs, scenarios, strict=True)),
        )

    def to_dict(self) -> dict[str, Any]:
        reports = [dict(report) for report in self.reports]
        summary: dict[str, Any] = {
            "suite_id": str(self.suite.get("id", "p87-supervisor-run-report-artifact")),
            "scenario_count": len(reports),
            "terminal_count": sum(1 for report in reports if report["terminal_classification"] == "terminal"),
            "resumable_count": sum(1 for report in reports if report["resumable_items"]),
            "needs_human_count": sum(1 for report in reports if report["status"] == ResumableSupervisorStopReason.NEEDS_HUMAN.value),
            "failed_guardrail_count": sum(
                1 for report in reports if report["status"] == ResumableSupervisorStopReason.FAILED_GUARDRAIL.value
            ),
            "no_safe_work_count": sum(1 for report in reports if report["status"] == ResumableSupervisorStopReason.NO_SAFE_WORK.value),
            **_ZERO_SIDE_EFFECT_COUNTERS,
        }
        summary["passed"] = (
            summary["scenario_count"] >= 6
            and summary["terminal_count"] >= 5
            and summary["resumable_count"] >= 1
            and summary["needs_human_count"] >= 1
            and summary["failed_guardrail_count"] >= 1
            and summary["no_safe_work_count"] >= 1
            and all(summary[key] == 0 for key in _ZERO_SIDE_EFFECT_COUNTERS)
        )
        payload = {
            "summary": summary,
            "claim_boundary": dict(_CLAIM_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "reports": reports,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_supervisor_run_report_artifact_fixture(path: str | Path) -> SupervisorRunReportArtifact:
    return SupervisorRunReportArtifact.from_fixture(path)


def render_supervisor_run_report_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Supervisor Run Report Artifact",
        "",
        (
            "P87 renders P86-style local/mock supervisor run state into an operator-facing report. "
            "It explains what happened, why the run stopped, what remains, and whether it is safe to continue."
        ),
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Terminal: {summary.get('terminal_count', 0)}",
        f"- Resumable: {summary.get('resumable_count', 0)}",
        f"- Needs human: {summary.get('needs_human_count', 0)}",
        f"- Failed guardrail: {summary.get('failed_guardrail_count', 0)}",
        f"- No safe work: {summary.get('no_safe_work_count', 0)}",
        f"- Executions: {summary.get('action_execution_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Reports",
        "",
    ]
    for report in _sequence(payload.get("reports", ())):
        if not isinstance(report, Mapping):
            continue
        completed = ", ".join(str(item.get("item_id")) for item in _mapping_sequence(report.get("completed_items")))
        blocked = ", ".join(str(item.get("item_id")) for item in _mapping_sequence(report.get("blocked_items")))
        resumable = ", ".join(str(item.get("item_id")) for item in _mapping_sequence(report.get("resumable_items")))
        lines.extend(
            [
                f"### {report.get('scenario_id', 'scenario')}",
                "",
                f"- Run ID: {report.get('run_id')}",
                f"- Status: {report.get('status')}",
                f"- Stop reason: {report.get('stop_reason')}",
                f"- Classification: {report.get('terminal_classification')}",
                f"- Completed: {completed or 'none'}",
                f"- Blocked: {blocked or 'none'}",
                f"- Resumable: {resumable or 'none'}",
                f"- Safety gates hit: {', '.join(str(item) for item in _sequence(report.get('safety_gates_hit', ()))) or 'none'}",
                f"- Next action: {_mapping(report.get('next_recommended_action')).get('action', 'none')}",
                "",
                "#### Human decision required",
                "",
                f"- Required: {_mapping(report.get('human_decision_required')).get('required', False)}",
                f"- Reason: {_mapping(report.get('human_decision_required')).get('reason', 'none')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Claim boundary",
            "",
            "- Local/mock report artifact only.",
            "- Consumes modeled P86 run state and deterministic fixture data.",
            "- No live APIs, credentials, network calls, shell execution, process spawning, agent spawning, production mutation, remediation execution, or action execution.",
            "- This is not unattended production operation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_supervisor_run_report_artifact_outputs(
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
        output_md_path.write_text(render_supervisor_run_report_markdown(payload), encoding="utf-8")


def _build_report(run: Mapping[str, Any], scenario: ResumableSupervisorScenario) -> Mapping[str, Any]:
    stop_reason = str(run.get("stop_reason", "unknown"))
    completed_ids = _unique_strings(_sequence(run.get("completed_item_ids", ())))
    skipped = _mapping_sequence(run.get("skipped_items"))
    cursor = int(_float(run.get("cursor"), 0.0))
    backlog_ids = [item.id for item in scenario.backlog]
    completed_set = set(completed_ids)
    skipped_ids = {str(item.get("item_id", "")) for item in skipped}
    resumable_ids = [
        item_id
        for item_id in backlog_ids[cursor:]
        if item_id not in completed_set and item_id not in skipped_ids and stop_reason in {"max_iterations", "budget_exhausted"}
    ]
    safety_gates_hit = _safety_gates_hit(stop_reason, skipped)
    human_decision = _human_decision_required(stop_reason, skipped)
    return {
        "scenario_id": str(run.get("scenario_id", scenario.id)),
        "run_id": str(run.get("run_id", scenario.run_id)),
        "status": stop_reason,
        "stop_reason": stop_reason,
        "terminal_classification": "terminal" if stop_reason in _TERMINAL_REASONS else "non_terminal",
        "completed_items": [{"item_id": item_id, "status": "completed"} for item_id in completed_ids],
        "skipped_items": [_skipped_summary(item) for item in skipped if item.get("reason") != "approval_required"],
        "blocked_items": [_blocked_summary(item) for item in skipped if item.get("reason") == "approval_required"],
        "resumable_items": [{"item_id": item_id, "status": "resumable", "cursor": cursor} for item_id in resumable_ids],
        "checkpoint_timeline": [_checkpoint_summary(item) for item in _mapping_sequence(run.get("checkpoints"))],
        "safety_gates_hit": safety_gates_hit,
        "failure_evidence": _failure_evidence(run, scenario),
        "next_recommended_action": _next_action(stop_reason),
        "next_recommended_wakeup": run.get("next_recommended_wakeup"),
        "human_decision_required": human_decision,
        "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        "audit_metadata": {
            **dict(_mapping(run.get("audit_metadata"))),
            "p87_report_artifact": True,
            "resumed_from_state": _mapping(run.get("resume_metadata")).get("resumed_from_state") is True,
        },
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }


def _safety_gates_hit(stop_reason: str, skipped: Sequence[Mapping[str, Any]]) -> list[str]:
    gates: list[str] = []
    if any(item.get("reason") == "insufficient_evidence" for item in skipped):
        gates.append("evidence_insufficiency")
    if any(item.get("reason") == "approval_required" for item in skipped):
        gates.append("approval_blocked")
    if stop_reason == ResumableSupervisorStopReason.FAILED_GUARDRAIL.value:
        gates.append("failure_streak")
    if stop_reason == ResumableSupervisorStopReason.BUDGET_EXHAUSTED.value:
        gates.append("budget_limit")
    if stop_reason == ResumableSupervisorStopReason.MAX_ITERATIONS.value:
        gates.append("max_iterations")
    return gates


def _next_action(stop_reason: str) -> Mapping[str, str]:
    if stop_reason == ResumableSupervisorStopReason.COMPLETED_ALL.value:
        return {"action": "archive_report", "reason": "terminal_success"}
    if stop_reason == ResumableSupervisorStopReason.MAX_ITERATIONS.value:
        return {"action": "resume_from_cursor", "reason": "iteration_limit_reached"}
    if stop_reason == ResumableSupervisorStopReason.BUDGET_EXHAUSTED.value:
        return {"action": "resume_after_budget_refresh", "reason": "budget_limit_reached"}
    if stop_reason == ResumableSupervisorStopReason.NEEDS_HUMAN.value:
        return {"action": "request_human_decision", "reason": "approval_required"}
    if stop_reason == ResumableSupervisorStopReason.FAILED_GUARDRAIL.value:
        return {"action": "review_guardrail_failure", "reason": "failure_streak"}
    return {"action": "recheck_backlog", "reason": "no_safe_local_work"}


def _human_decision_required(stop_reason: str, skipped: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    blocked_ids = [str(item.get("item_id")) for item in skipped if item.get("reason") == "approval_required"]
    if stop_reason == ResumableSupervisorStopReason.NEEDS_HUMAN.value or blocked_ids:
        return {"required": True, "reason": "approval_required", "blocked_item_ids": blocked_ids}
    return {"required": False, "reason": "none", "blocked_item_ids": []}


def _failure_evidence(run: Mapping[str, Any], scenario: ResumableSupervisorScenario) -> list[Mapping[str, Any]]:
    selected_ids = set(_unique_strings(_sequence(run.get("selected_item_ids", ()))))
    if str(run.get("stop_reason")) != ResumableSupervisorStopReason.FAILED_GUARDRAIL.value:
        return []
    return [
        {"item_id": item.id, "result": item.mock_step_result, "executed": False}
        for item in scenario.backlog
        if item.id in selected_ids and item.mock_step_result == "failed"
    ]


def _checkpoint_summary(item: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "checkpoint_id": str(item.get("checkpoint_id", "")),
        "event": str(item.get("event", "")),
        "cursor": int(_float(item.get("cursor"), 0.0)),
        "completed_item_ids": _unique_strings(_sequence(item.get("completed_item_ids", ()))),
        "skipped_item_ids": _unique_strings(_sequence(item.get("skipped_item_ids", ()))),
    }


def _skipped_summary(item: Mapping[str, Any]) -> Mapping[str, str]:
    return {
        "item_id": str(item.get("item_id", "")),
        "status": "skipped",
        "reason": str(item.get("reason", "")),
        "blocked_by": str(item.get("blocked_by", "")),
    }


def _blocked_summary(item: Mapping[str, Any]) -> Mapping[str, str]:
    return {
        "item_id": str(item.get("item_id", "")),
        "status": "blocked",
        "reason": str(item.get("reason", "")),
        "blocked_by": str(item.get("blocked_by", "")),
    }


def _unique_strings(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _mapping_sequence(value: Any) -> Sequence[Mapping[str, Any]]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "SupervisorRunReportArtifact",
    "evaluate_supervisor_run_report_artifact_fixture",
    "render_supervisor_run_report_markdown",
    "write_supervisor_run_report_artifact_outputs",
]
