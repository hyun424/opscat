"""P52 failure mining loop for benchmark-driven agent improvement."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.operator_judgment_benchmark_v2 import build_operator_judgment_benchmark_v2_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "failure_mining_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_FAILURE_META = {
    "detection_failure": {
        "priority": "P0",
        "owner_lane": "detection",
        "title": "Improve incident detection recall",
        "acceptance": "Benchmark detection_recall improves and the source case is detected without unsafe action.",
    },
    "root_cause_failure": {
        "priority": "P0",
        "owner_lane": "root_cause",
        "title": "Improve top-1 root-cause hypothesis accuracy",
        "acceptance": "The expected top hypothesis becomes top-1 while preserving evidence and counter-evidence.",
    },
    "evidence_gap": {
        "priority": "P1",
        "owner_lane": "evidence",
        "title": "Strengthen evidence collection and missing-evidence handling",
        "acceptance": "Evidence quality reaches at least 0.9 for affected cases with support, counter, and missing evidence recorded.",
    },
    "route_failure": {
        "priority": "P1",
        "owner_lane": "policy",
        "title": "Correct safe route selection",
        "acceptance": "Predicted route matches expected route and unsafe auto-execute remains zero.",
    },
    "rerank_failure": {
        "priority": "P1",
        "owner_lane": "investigation",
        "title": "Improve anti-anchoring re-ranking",
        "acceptance": "Contradicted initial hypotheses are demoted when new read-only evidence arrives.",
    },
    "recovery_verification_gap": {
        "priority": "P1",
        "owner_lane": "recovery_verification",
        "title": "Expand recovery verification coverage",
        "acceptance": "Affected cases include explicit post-check recovery criteria or escalation evidence.",
    },
}
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass(frozen=True)
class FailureMiningLoopReport:
    source_summary: Mapping[str, Any]
    source_scorecard: Mapping[str, Any]
    source_cases: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        clusters = _clusters(self.source_cases)
        tickets = _tickets(clusters)
        regression_cases = _regression_cases(clusters)
        unsafe = sum(1 for ticket in tickets if ticket["action_boundary"]["unsafe_action_allowed"])
        highest = _highest_priority(tickets)
        payload = {
            "summary": {
                "source_case_count": int(self.source_summary.get("case_count", len(self.source_cases))),
                "failure_cluster_count": len(clusters),
                "improvement_ticket_count": len(tickets),
                "regression_case_count": len(regression_cases),
                "highest_priority": highest,
                "unsafe_action_count": unsafe,
                "passed": bool(clusters) and bool(tickets) and bool(regression_cases) and unsafe == 0,
            },
            "source_scorecard": dict(self.source_scorecard),
            "failure_clusters": clusters,
            "improvement_tickets": tickets,
            "regression_cases": regression_cases,
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_failure_mining_loop_report(cases_path: str | Path) -> FailureMiningLoopReport:
    benchmark = build_operator_judgment_benchmark_v2_report(cases_path).to_dict()
    return FailureMiningLoopReport(
        source_summary=_mapping(benchmark.get("summary")),
        source_scorecard=_mapping(benchmark.get("scorecard")),
        source_cases=tuple(case for case in _sequence(benchmark.get("cases", ())) if isinstance(case, Mapping)),
    )


def render_failure_mining_loop_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Failure Mining Loop",
        "",
        "Turns benchmark failures into prioritized improvement tickets and deterministic regression cases.",
        "",
        "## Summary",
        f"- Source cases: {summary.get('source_case_count')}",
        f"- Failure clusters: {summary.get('failure_cluster_count')}",
        f"- Improvement tickets: {summary.get('improvement_ticket_count')}",
        f"- Regression cases: {summary.get('regression_case_count')}",
        f"- Highest priority: {summary.get('highest_priority')}",
        "",
        "## Failure clusters",
    ]
    for failure, cluster in sorted(_mapping(payload.get("failure_clusters")).items()):
        if isinstance(cluster, Mapping):
            lines.append(f"- {failure}: count={cluster.get('count')} cases={', '.join(str(case) for case in _sequence(cluster.get('case_ids', ())))}")
    lines.extend(["", "## Improvement tickets"])
    for ticket in _sequence(payload.get("improvement_tickets", ())):
        if isinstance(ticket, Mapping):
            lines.append(f"- `{ticket.get('ticket_id')}` {ticket.get('priority')} {ticket.get('title')}")
    lines.extend(["", "## Regression cases"])
    for case in _sequence(payload.get("regression_cases", ())):
        if isinstance(case, Mapping):
            lines.append(f"- `{case.get('regression_id')}` source={case.get('source_case_id')} failure={case.get('failure_type')}")
    lines.extend(["", "## Boundary", "- Mining creates local tickets and regression cases only; it never executes production actions."])
    return "\n".join(lines) + "\n"


def write_failure_mining_loop_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_failure_mining_loop_markdown(payload), encoding="utf-8")


def _clusters(cases: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        for failure in _sequence(case.get("failures", ())):
            if isinstance(failure, str) and failure in _FAILURE_META:
                grouped[failure].append(case)
    return {failure: _cluster(failure, rows) for failure, rows in sorted(grouped.items())}


def _cluster(failure: str, cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    meta = _FAILURE_META[failure]
    return {
        "failure_type": failure,
        "count": len(cases),
        "case_ids": [str(case.get("case_id")) for case in cases],
        "priority": meta["priority"],
        "owner_lane": meta["owner_lane"],
        "operator_risk": _operator_risk(failure, len(cases)),
        "evidence_refs": [_evidence_ref(case) for case in cases],
    }


def _tickets(clusters: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    tickets: list[dict[str, Any]] = []
    for failure, cluster in sorted(clusters.items(), key=lambda item: (_PRIORITY_ORDER.get(str(item[1].get("priority")), 9), item[0])):
        meta = _FAILURE_META[failure]
        tickets.append(
            {
                "ticket_id": f"P52-{len(tickets) + 1:03d}-{failure.replace('_', '-')}",
                "failure_type": failure,
                "priority": str(cluster.get("priority", meta["priority"])),
                "owner_lane": str(cluster.get("owner_lane", meta["owner_lane"])),
                "title": meta["title"],
                "source_case_ids": list(_sequence(cluster.get("case_ids", ()))),
                "acceptance_criteria": [meta["acceptance"], "Full verification remains green.", "Unsafe auto-execute, production execution, and live calls remain zero."],
                "action_boundary": {
                    "unsafe_action_allowed": False,
                    "production_execution_allowed": False,
                    "live_call_allowed": False,
                    "safe_actions": ["add regression fixture", "improve scoring logic", "update offline benchmark"],
                    "blocked_actions": ["production rollback", "restart production", "write config", "call live connector"],
                },
            }
        )
    return tickets


def _regression_cases(clusters: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for failure, cluster in sorted(clusters.items()):
        for case_id in _sequence(cluster.get("case_ids", ())) :
            cases.append(
                {
                    "regression_id": f"p52-regression-{failure.replace('_', '-')}-{case_id}",
                    "failure_type": failure,
                    "source_case_id": str(case_id),
                    "expected_fix_signal": _FAILURE_META[failure]["acceptance"],
                    "must_keep_safety_zero": True,
                }
            )
    return cases


def _operator_risk(failure: str, count: int) -> str:
    if failure in {"detection_failure", "root_cause_failure"}:
        return "critical"
    if failure in {"route_failure", "recovery_verification_gap"} or count >= 2:
        return "high"
    return "medium"


def _evidence_ref(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id", "unknown")),
        "predicted_top_hypothesis": str(case.get("predicted_top_hypothesis", "unknown")),
        "expected_top_hypothesis": str(case.get("expected_top_hypothesis", "unknown")),
        "predicted_route": str(case.get("predicted_route", "unknown")),
        "expected_route": str(case.get("expected_route", "unknown")),
    }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _highest_priority(tickets: Sequence[Mapping[str, Any]]) -> str:
    if not tickets:
        return "none"
    return min((str(ticket.get("priority", "P3")) for ticket in tickets), key=lambda priority: _PRIORITY_ORDER.get(priority, 99))
