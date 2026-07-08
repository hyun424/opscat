"""P53 failure-driven improvement pack for closing mined benchmark gaps."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.failure_mining_loop import build_failure_mining_loop_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "improvement_planning_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class FailureDrivenImprovementPackReport:
    mined_payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        clusters = _mapping(self.mined_payload.get("failure_clusters"))
        tickets = tuple(ticket for ticket in _sequence(self.mined_payload.get("improvement_tickets", ())) if isinstance(ticket, Mapping))
        regression_cases = tuple(case for case in _sequence(self.mined_payload.get("regression_cases", ())) if isinstance(case, Mapping))
        plans = tuple(_build_plan(ticket, _mapping(clusters.get(str(ticket.get("failure_type"))))) for ticket in tickets)
        evidence_probes = [probe for plan in plans for probe in _sequence(plan.get("evidence_probes", ())) if isinstance(probe, Mapping)]
        recovery_checks = [check for plan in plans for check in _sequence(plan.get("recovery_checks", ())) if isinstance(check, Mapping)]
        projected = _projected_score_impact(clusters, plans)
        unsafe = sum(1 for plan in plans if _mapping(plan.get("action_boundary")).get("unsafe_action_allowed"))
        payload = {
            "summary": {
                "source_failure_cluster_count": len(clusters),
                "improvement_plan_count": len(plans),
                "evidence_probe_count": len(evidence_probes),
                "recovery_check_count": len(recovery_checks),
                "regression_case_count": len(regression_cases),
                "unsafe_action_count": unsafe,
                "passed": bool(plans) and len(evidence_probes) >= 3 and len(recovery_checks) >= 4 and bool(regression_cases) and unsafe == 0,
            },
            "projected_score_impact": projected,
            "improvement_plans": list(plans),
            "regression_cases": [dict(case) for case in regression_cases],
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_failure_driven_improvement_pack_report(cases_path: str | Path) -> FailureDrivenImprovementPackReport:
    mined = build_failure_mining_loop_report(cases_path).to_dict()
    return FailureDrivenImprovementPackReport(mined)


def render_failure_driven_improvement_pack_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    projected = _mapping(payload.get("projected_score_impact"))
    lines = [
        "# OpsCat Failure-Driven Improvement Pack",
        "",
        "Converts mined benchmark failures into concrete evidence probes, recovery checks, regression cases, and validation commands.",
        "",
        "## Summary",
        f"- Failure clusters: {summary.get('source_failure_cluster_count')}",
        f"- Improvement plans: {summary.get('improvement_plan_count')}",
        f"- Evidence probes: {summary.get('evidence_probe_count')}",
        f"- Recovery checks: {summary.get('recovery_check_count')}",
        f"- Regression cases: {summary.get('regression_case_count')}",
        "",
        "## Projected score impact",
    ]
    for failure, impact in sorted(projected.items()):
        if isinstance(impact, Mapping):
            lines.append(f"- {failure}: before={impact.get('before')} after={impact.get('after')}")
    lines.extend(["", "## Evidence probes"])
    for plan in _sequence(payload.get("improvement_plans", ())):
        if isinstance(plan, Mapping):
            for probe in _sequence(plan.get("evidence_probes", ())):
                if isinstance(probe, Mapping):
                    lines.append(f"- `{plan.get('failure_type')}` {probe.get('probe_id')}: {probe.get('query')}")
    lines.extend(["", "## Recovery checks"])
    for plan in _sequence(payload.get("improvement_plans", ())):
        if isinstance(plan, Mapping):
            for check in _sequence(plan.get("recovery_checks", ())):
                if isinstance(check, Mapping):
                    lines.append(f"- `{plan.get('failure_type')}` {check.get('check_id')}: {check.get('criterion')}")
    lines.extend(["", "## Regression cases"])
    for case in _sequence(payload.get("regression_cases", ())):
        if isinstance(case, Mapping):
            lines.append(f"- `{case.get('regression_id')}` source={case.get('source_case_id')}")
    lines.extend(["", "## Boundary", "- Planning artifacts only; no live calls, no production execution, and no remediation execution."])
    return "\n".join(lines) + "\n"


def write_failure_driven_improvement_pack_outputs(
    payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_failure_driven_improvement_pack_markdown(payload), encoding="utf-8")


def _build_plan(ticket: Mapping[str, Any], cluster: Mapping[str, Any]) -> dict[str, Any]:
    failure_type = str(ticket.get("failure_type", "unknown"))
    case_ids = tuple(str(case_id) for case_id in _sequence(ticket.get("source_case_ids", ())))
    return {
        "plan_id": str(ticket.get("ticket_id", f"P53-{failure_type}")),
        "failure_type": failure_type,
        "priority": str(ticket.get("priority", "P2")),
        "owner_lane": str(ticket.get("owner_lane", "judgment_quality")),
        "source_case_ids": list(case_ids),
        "operator_risk": str(cluster.get("operator_risk", "medium")),
        "evidence_probes": _evidence_probes(failure_type, case_ids),
        "recovery_checks": _recovery_checks(failure_type, case_ids),
        "acceptance_criteria": _acceptance_criteria(failure_type),
        "validation_command": " ".join(
            [
                "UV_CACHE_DIR=/private/tmp/uv-cache",
                "uv run --no-sync --extra dev pytest -q",
                "tests/test_operator_judgment_benchmark_v2.py",
                "tests/test_failure_mining_loop.py",
                "tests/test_failure_driven_improvement_pack.py",
            ]
        ),
        "action_boundary": {
            "unsafe_action_allowed": False,
            "production_execution_allowed": False,
            "live_call_allowed": False,
            "safe_actions": ["add offline fixture evidence", "add post-check criteria", "rerun local benchmark"],
            "blocked_actions": ["call live connector", "restart production", "rollback production", "write production config"],
        },
    }


def _evidence_probes(failure_type: str, case_ids: Sequence[str]) -> list[dict[str, str]]:
    probes: list[dict[str, str]] = []
    if failure_type == "evidence_gap":
        for case_id in case_ids:
            probes.extend(
                [
                    {
                        "probe_id": f"{case_id}-counter-source-confirmation",
                        "mode": "read_only_fixture",
                        "query": "Add independent counter/source confirmation for weak-evidence traffic spike cases.",
                    },
                    {
                        "probe_id": f"{case_id}-bot-distribution",
                        "mode": "read_only_fixture",
                        "query": "Add bot/user-agent distribution evidence to separate organic traffic from automated load.",
                    },
                    {
                        "probe_id": f"{case_id}-autoscaling-event",
                        "mode": "read_only_fixture",
                        "query": "Add autoscaling event evidence to explain whether capacity response occurred.",
                    },
                ]
            )
    else:
        for case_id in case_ids:
            probes.append(
                {
                    "probe_id": f"{case_id}-{failure_type}-context",
                    "mode": "read_only_fixture",
                    "query": "Preserve source benchmark context for recovery-check planning.",
                }
            )
    return probes


def _recovery_checks(failure_type: str, case_ids: Sequence[str]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if failure_type == "recovery_verification_gap":
        for case_id in case_ids:
            checks.extend(
                [
                    {
                        "check_id": f"{case_id}-primary-slo-postcheck",
                        "mode": "mock_postcheck",
                        "criterion": "Primary SLO/error-rate metric returns below incident threshold after proposed action or escalation.",
                    },
                    {
                        "check_id": f"{case_id}-guardrail-postcheck",
                        "mode": "mock_postcheck",
                        "criterion": "Guardrail metric confirms no new error class or capacity regression was introduced.",
                    },
                ]
            )
    else:
        for case_id in case_ids:
            checks.append(
                {
                    "check_id": f"{case_id}-{failure_type}-monitoring-check",
                    "mode": "mock_postcheck",
                    "criterion": "Continue read-only observation until evidence quality threshold is reached.",
                }
            )
    return checks


def _acceptance_criteria(failure_type: str) -> list[str]:
    if failure_type == "evidence_gap":
        return [
            "Affected benchmark cases include at least one independent counter-evidence source.",
            "Evidence quality for affected cases is projected to reach at least 0.9.",
            "Unsafe auto-execute, production execution, and live calls remain zero.",
        ]
    if failure_type == "recovery_verification_gap":
        return [
            "Affected benchmark cases include explicit primary SLO post-check criteria.",
            "Affected benchmark cases include guardrail post-check criteria or escalation route.",
            "Unsafe auto-execute, production execution, and live calls remain zero.",
        ]
    return ["Affected benchmark cases receive a deterministic regression case.", "Full verification remains green."]


def _projected_score_impact(clusters: Mapping[str, Any], plans: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    planned = {str(plan.get("failure_type")) for plan in plans}
    impact: dict[str, dict[str, int]] = {}
    for failure_type, cluster in clusters.items():
        if isinstance(cluster, Mapping):
            before = int(cluster.get("count", 0))
            impact[str(failure_type)] = {"before": before, "after": 0 if str(failure_type) in planned else before}
    return impact


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
