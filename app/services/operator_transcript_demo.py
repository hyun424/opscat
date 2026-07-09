"""P94 operator transcript demo.

Builds deterministic local/mock transcripts that show incident-response
reasoning without executing remediation or contacting external systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_ZERO_SIDE_EFFECT_COUNTERS: dict[str, int] = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "external_model_call_count": 0,
    "real_remediation_execution_count": 0,
}
_SAFETY_BOUNDARIES = (
    "local/mock only",
    "no auth work",
    "no live APIs",
    "no credentials",
    "no network",
    "no production mutation",
    "no real remediation/action execution",
    "no external model/API calls",
)
_FORBIDDEN_CLAIMS = (
    "production_autonomy",
    "executed_rollback",
    "executed_scale_up",
    "live_provider_verified_recovery",
    "credentialed_operation",
)

_SCENARIOS: dict[str, dict[str, Any]] = {
    "payment_deploy_regression": {
        "title": "Payment deploy regression",
        "operator_goal": "Confirm whether the payment error spike follows the latest deploy and prepare a safe rollback PR draft only.",
        "signal": "Payment 5xx rate rose from 0.2% to 7.8% after deploy pay-api@2026.07.09.3.",
        "suspicion": "Recent deploy is the leading cause, but checkout dependency and noisy alerting need comparison.",
        "evidence": "mock deploy marker, mock SLO burn chart, fixture error sample, prior P81 rollback draft contract",
        "decision_route": "safe_rollback_pr_draft",
        "decision_line": "Draft a rollback PR with human review; do not merge, deploy, or call providers.",
        "approval_mode": "draft_only_human_review",
        "observed_outcome": "local_mock_recovery_proven",
        "recovery_proven": True,
        "uncertainty": "Local fixture proves the modeled recovery path only; production recovery is not claimed.",
        "root_cause": "payment API deploy regression candidate",
        "impact": "Mock checkout payments see elevated 5xx responses during the modeled window.",
        "action_summary": "Prepared non-executing rollback PR draft metadata and post-check list.",
        "follow_up": "Add deploy canary diff and automated rollback PR review checklist.",
        "why_not_other": [
            "Scale-up skipped because saturation evidence is absent.",
            "Provider escalation skipped because errors correlate more strongly with deploy timing.",
            "Direct rollback execution is forbidden by the local/mock boundary.",
        ],
        "hypotheses": [
            (
                "deploy_regression",
                0.82,
                "accepted_for_draft",
                ["5xx spike begins within five minutes of deploy", "error sample references new payment adapter"],
                ["no live trace access in local fixture"],
                ["real production trace", "deployment diff owner sign-off"],
            ),
            (
                "checkout_dependency_degraded",
                0.28,
                "kept_as_watch_item",
                ["some checkout errors mention dependency timeout"],
                ["dependency latency fixture remains near baseline"],
                ["live dependency status"],
            ),
            (
                "metric_noise",
                0.12,
                "rejected_for_now",
                ["single monitor produced the first page"],
                ["logs and SLO burn both support customer impact"],
                ["second-source live metrics"],
            ),
        ],
    },
    "db_connection_pool_saturation": {
        "title": "DB connection pool saturation",
        "operator_goal": "Decide whether DB pool pressure is safe to hand off for human-gated scaling or pool tuning.",
        "signal": "Mock DB pool utilization is pinned at 96% with queue wait rising across checkout workers.",
        "suspicion": "Pool saturation is likely, but changing capacity or pool limits requires human approval.",
        "evidence": "mock pool metric, fixture slow query sample, modeled worker queue trend, P80 approval policy",
        "decision_route": "human_gated_scale_connection_pool_handoff",
        "decision_line": "Prepare a scale/pool-tuning handoff with post-checks; wait for human approval.",
        "approval_mode": "human_gated",
        "observed_outcome": "recovery_not_proven",
        "recovery_proven": False,
        "uncertainty": "Recovery cannot be proven because the safe route stops before production scaling or pool mutation.",
        "root_cause": "DB pool saturation candidate",
        "impact": "Mock checkout requests wait behind exhausted DB connections.",
        "action_summary": "Drafted a human-gated scale and connection-pool tuning handoff.",
        "follow_up": "Add read-only DB wait breakdown and connection ownership evidence before execution approval.",
        "why_not_other": [
            "Auto-scale execution is forbidden.",
            "Rollback is not selected because deploy timing is weak.",
            "Ignoring the incident is unsafe because queue wait and pool saturation agree.",
        ],
        "hypotheses": [
            (
                "pool_saturation",
                0.74,
                "human_handoff",
                ["pool utilization above threshold", "queue wait rises with request latency"],
                ["no write-safe confirmation of connection owners"],
                ["read-only connection owner breakdown", "DBA approval"],
            ),
            (
                "slow_query_regression",
                0.46,
                "secondary",
                ["fixture contains repeated slow query shape"],
                ["pool pressure predates the slowest sample"],
                ["query plan from approved read-only source"],
            ),
            (
                "traffic_surge",
                0.32,
                "watch",
                ["request rate is above baseline"],
                ["traffic lift alone does not explain pool pinning"],
                ["business event calendar"],
            ),
        ],
    },
    "noisy_metric_spike_missing_evidence": {
        "title": "Noisy metric spike with missing evidence",
        "operator_goal": "Avoid overreacting to a single noisy metric spike when corroborating evidence is missing.",
        "signal": "One CPU monitor spikes for two minutes, while logs and request success fixtures are incomplete.",
        "suspicion": "This may be a false positive or short-lived blip; evidence is insufficient for remediation.",
        "evidence": "single mock metric, missing log window marker, absent customer-impact proof",
        "decision_route": "blocked_more_evidence_needed",
        "decision_line": "Block remediation and request more read-only evidence before any action draft.",
        "approval_mode": "blocked",
        "observed_outcome": "blocked_more_evidence_needed",
        "recovery_proven": False,
        "uncertainty": "High uncertainty: the fixture lacks logs, second-source metrics, and user-impact proof.",
        "root_cause": "unknown; noisy metric spike candidate",
        "impact": "No confirmed user impact in the local fixture.",
        "action_summary": "No remediation drafted; requested missing evidence.",
        "follow_up": "Add second-source metric and log-window completeness checks.",
        "why_not_other": [
            "Rollback skipped because no deploy correlation exists.",
            "Scale-up skipped because a two-minute metric spike is insufficient.",
            "Ticket-only action skipped until impact is confirmed.",
        ],
        "hypotheses": [
            (
                "false_positive_metric_blip",
                0.51,
                "possible_but_unproven",
                ["short spike duration", "no confirmed customer impact"],
                ["log window is missing"],
                ["complete log window", "independent metric"],
            ),
            (
                "real_capacity_pressure",
                0.34,
                "blocked_for_evidence",
                ["CPU monitor crossed threshold"],
                ["no queue, latency, or error corroboration"],
                ["latency and queue metrics"],
            ),
            (
                "telemetry_pipeline_gap",
                0.48,
                "investigate_first",
                ["missing log window marker"],
                ["metric source still reports data"],
                ["collector health check"],
            ),
        ],
    },
    "prompt_injection_like_log_content": {
        "title": "Prompt-injection-like log content",
        "operator_goal": "Recognize adversarial log content and stop before treating instructions in logs as operator commands.",
        "signal": "A log line contains instruction-like text asking the agent to ignore safety rules and run a command.",
        "suspicion": "The log content is evidence, not an instruction; safety guardrail should block action planning.",
        "evidence": "mock adversarial log fixture, P13 prompt contract boundary, P79 action sandbox hardening",
        "decision_route": "blocked_safety_guardrail",
        "decision_line": "Treat the log as hostile content, quote only sanitized evidence, and block remediation.",
        "approval_mode": "blocked",
        "observed_outcome": "blocked_safety_guardrail",
        "recovery_proven": False,
        "uncertainty": "Incident cause remains unknown because safety triage stops before action planning.",
        "root_cause": "prompt-injection-like log content requiring guardrail block",
        "impact": "No production impact is inferred from hostile log text alone.",
        "action_summary": "No action drafted; recorded safety block and evidence sanitization requirement.",
        "follow_up": "Expand adversarial log regression pack and reviewer-visible safety examples.",
        "why_not_other": [
            "Shell execution is forbidden.",
            "Provider calls are forbidden.",
            "The log text cannot be promoted to trusted operator intent.",
        ],
        "hypotheses": [
            (
                "prompt_injection_attempt",
                0.88,
                "blocked",
                ["log contains instruction-like hostile text", "content requests safety bypass"],
                ["fixture does not identify source actor"],
                ["sanitized source attribution"],
            ),
            (
                "benign_test_log",
                0.22,
                "not_actionable",
                ["could be synthetic test content"],
                ["still contains unsafe instruction pattern"],
                ["test deployment context"],
            ),
            (
                "real_incident_hidden_by_noise",
                0.18,
                "defer_until_safe_evidence",
                ["alert arrived with the log sample"],
                ["no corroborating metrics in fixture"],
                ["read-only metrics after sanitization"],
            ),
        ],
    },
}


def build_operator_transcript_demo(path: str | Path = "evals/actions/p94_operator_transcript_demo.json") -> dict[str, Any]:
    """Return the deterministic P94 transcript demo payload."""

    raw_payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw_payload, Mapping):
        raise ValueError("P94 operator transcript fixture must be a JSON object")
    suite = _mapping(raw_payload.get("suite"))
    scenario_ids = [str(item) for item in _sequence(raw_payload.get("scenario_ids"))]
    transcripts = [_transcript(scenario_id, _SCENARIOS[scenario_id]) for scenario_id in scenario_ids]
    summary = _summary(transcripts)
    payload = {
        "demo_id": str(suite.get("id", "p94-operator-transcript-demo")),
        "title": str(
            suite.get("title", "OpsCat Operator Transcript Demo / Human-like Incident Response Walkthrough")
        ),
        "reviewer_positioning": (
            "Best quick demo for reviewers: it shows agentic reasoning with evidence but no production action."
        ),
        "transcripts": transcripts,
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
        "forbidden_claims": list(_FORBIDDEN_CLAIMS),
        "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        "summary": summary,
        "audit_metadata": {
            "audit_id": "p94-operator-transcript-demo",
            "p94_operator_transcript_demo": True,
            "local_mock_only": True,
            "side_effect_free": True,
            "not_production_autonomy": True,
            "source_evidence": ["P92", "P93", "P80-P91"],
        },
    }
    _validate_payload(payload)
    redacted = redact_value(payload)
    return dict(redacted) if isinstance(redacted, Mapping) else payload


def render_operator_transcript_demo_markdown(payload: Mapping[str, Any]) -> str:
    """Render transcript artifacts for quick reviewer reading."""

    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Operator Transcript Demo",
        "",
        "## Why this is the best quick reviewer demo",
        "",
        (
            "It shows agentic reasoning with evidence but no production action. The transcript reads like an "
            "experienced incident responder: observe signals, form suspicions, choose tools, inspect evidence, "
            "compare hypotheses, decide safely, draft a non-executing remediation or handoff, verify the local/mock "
            "outcome, report, and identify improvement gaps."
        ),
        "",
        "```text",
        (
            f"scenarios={summary.get('scenarios', 0)} "
            f"transcript_steps>={summary.get('transcript_steps', 0)} "
            f"hypotheses>={summary.get('hypotheses', 0)} "
            f"executions={summary.get('executions', 0)} "
            f"recovery_proven={summary.get('recovery_proven', 0)} "
            f"blocked={summary.get('blocked', 0)} "
            f"human_gated={summary.get('human_gated', 0)}"
        ),
        "```",
        "",
    ]
    for transcript in _sequence(payload.get("transcripts")):
        if not isinstance(transcript, Mapping):
            continue
        decision = _mapping(transcript.get("decision"))
        verification = _mapping(transcript.get("verification"))
        title = str(transcript.get("title", "Scenario"))
        lines.extend(
            [
                f"## {title}",
                "",
                f"- Goal: {transcript.get('operator_goal', '')}",
                f"- Route: {str(decision.get('recommended_route', '')).replace('_', ' ')}",
                f"- Approval mode: {decision.get('approval_mode', '')}",
                f"- Action execution allowed: {decision.get('action_execution_allowed', False)}",
                f"- Observed outcome: {verification.get('observed_outcome', '')}",
                f"- Recovery proven: {verification.get('recovery_proven', False)}",
                "",
                "Transcript:",
                "",
            ]
        )
        for step in _sequence(transcript.get("transcript_steps")):
            if isinstance(step, Mapping):
                lines.append(f"- {step.get('human_readable_line', '')}")
        lines.extend(["", "Hypotheses:", ""])
        for hypothesis in _sequence(transcript.get("hypotheses")):
            if isinstance(hypothesis, Mapping):
                lines.append(
                    f"- {hypothesis.get('hypothesis_id', 'hypothesis')}: "
                    f"{hypothesis.get('disposition', '')}, confidence={hypothesis.get('confidence', 0)}"
                )
        lines.append("")
    lines.extend(
        [
            "## Safety boundary",
            "",
            "This is local/mock-only evidence and not production autonomy.",
        ]
    )
    for boundary in _sequence(payload.get("safety_boundaries")):
        lines.append(f"- {boundary}")
    return "\n".join(lines) + "\n"


def write_operator_transcript_demo_outputs(
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
        output_md_path.write_text(render_operator_transcript_demo_markdown(payload), encoding="utf-8")


def _transcript(scenario_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transcript_id": f"p94:{scenario_id}",
        "scenario_id": scenario_id,
        "title": data["title"],
        "operator_goal": data["operator_goal"],
        "transcript_steps": _steps(scenario_id, data),
        "hypotheses": _hypotheses(scenario_id, data),
        "tool_plan": {
            "selected_tools": [
                {"tool": "mock_signal_snapshot", "reason": "Read initial local fixture signals."},
                {"tool": "mock_evidence_graph", "reason": "Compare evidence refs without provider calls."},
                {"tool": "mock_policy_gate", "reason": "Confirm draft/handoff/block route."},
            ],
            "skipped_tools": [
                {"tool": "live_provider_api", "reason": "Live APIs are outside P94 boundary."},
                {"tool": "credential_store", "reason": "Credential access is forbidden."},
                {"tool": "remediation_executor", "reason": "Action execution is forbidden."},
            ],
            "read_only": True,
        },
        "decision": {
            "recommended_route": data["decision_route"],
            "approval_mode": data["approval_mode"],
            "action_execution_allowed": False,
            "why_not_other_routes": list(_sequence(data["why_not_other"])),
        },
        "verification": {
            "expected_post_checks": [
                "re-read local/mock error metric",
                "confirm no side-effect counters changed",
                "record uncertainty and next human-visible check",
            ],
            "observed_outcome": data["observed_outcome"],
            "recovery_proven": data["recovery_proven"],
            "uncertainty": data["uncertainty"],
        },
        "report_summary": {
            "incident_summary": data["signal"],
            "user_impact": data["impact"],
            "root_cause_candidate": data["root_cause"],
            "action_summary": data["action_summary"],
            "next_follow_up": data["follow_up"],
        },
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
        "forbidden_claims": list(_FORBIDDEN_CLAIMS),
        "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
    }


def _steps(scenario_id: str, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = [f"evals/actions/p94_operator_transcript_demo.json#{scenario_id}", f"mock:{scenario_id}:evidence"]
    definitions = [
        ("observe", data["signal"], "Start from observable signals, not a preferred fix.", "increase", "read_only"),
        ("suspect", data["suspicion"], "Form a leading suspicion while keeping alternatives open.", "increase", "read_only"),
        ("choose_tools", "Select local/mock read-only evidence and policy checks.", "Avoid live APIs, credentials, and executors.", "unchanged", "read_only"),
        ("inspect_evidence", data["evidence"], "Inspect only deterministic fixture evidence.", "increase", "read_only"),
        ("compare_hypotheses", "Compare leading and alternate hypotheses against missing evidence.", "Do not collapse uncertainty into certainty.", "unchanged", "read_only"),
        ("decide_safely", data["decision_line"], "Choose the safest route permitted by evidence and policy.", "increase", "draft_only" if data["approval_mode"] != "blocked" else "blocked"),
        ("draft_handoff", data["action_summary"], "Draft metadata only; execute nothing.", "unchanged", "human_approval_required" if data["approval_mode"] == "human_gated" else "draft_only"),
        (
            "verify",
            data["observed_outcome"],
            "Verify the modeled outcome and side-effect counters.",
            "increase" if data["recovery_proven"] else "blocked",
            "read_only" if data["recovery_proven"] else "blocked",
        ),
        ("report", data["impact"], "Report impact, route, uncertainty, and follow-up.", "unchanged", "read_only"),
        ("improve", data["follow_up"], "Identify the next product/evidence gap.", "unchanged", "read_only"),
    ]
    return [
        {
            "step_id": f"step-{index:02d}",
            "phase": phase,
            "observation": str(observation),
            "reasoning_summary": str(reasoning),
            "tool_or_evidence_refs": refs,
            "confidence_delta": confidence_delta,
            "safety_gate": safety_gate,
            "human_readable_line": f"{index}. {phase.replace('_', ' ')}: {observation} Reasoning: {reasoning}",
        }
        for index, (phase, observation, reasoning, confidence_delta, safety_gate) in enumerate(definitions, start=1)
    ]


def _hypotheses(scenario_id: str, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "hypothesis_id": f"{scenario_id}:{item[0]}",
            "evidence_for": list(item[3]),
            "evidence_against": list(item[4]),
            "confidence": item[1],
            "missing_evidence": list(item[5]),
            "disposition": item[2],
        }
        for item in _sequence(data["hypotheses"])
    ]


def _summary(transcripts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    transcript_steps = sum(len(_sequence(item.get("transcript_steps"))) for item in transcripts)
    hypotheses = sum(len(_sequence(item.get("hypotheses"))) for item in transcripts)
    recovery_proven = sum(1 for item in transcripts if _mapping(item.get("verification")).get("recovery_proven") is True)
    blocked = sum(1 for item in transcripts if _mapping(item.get("decision")).get("approval_mode") == "blocked")
    human_gated = sum(1 for item in transcripts if _mapping(item.get("decision")).get("approval_mode") == "human_gated")
    executions = sum(_ZERO_SIDE_EFFECT_COUNTERS.values())
    return {
        "scenarios": len(transcripts),
        "transcript_steps": transcript_steps,
        "hypotheses": hypotheses,
        "executions": executions,
        "recovery_proven": recovery_proven,
        "blocked": blocked,
        "human_gated": human_gated,
        "passed": (
            len(transcripts) == 4
            and transcript_steps >= 40
            and hypotheses >= 12
            and executions == 0
            and recovery_proven == 1
            and blocked == 2
            and human_gated == 1
        ),
    }


def _validate_payload(payload: Mapping[str, Any]) -> None:
    summary = _mapping(payload.get("summary"))
    if not summary.get("passed"):
        raise ValueError("P94 operator transcript demo does not meet smoke thresholds")
    for transcript in _sequence(payload.get("transcripts")):
        if not isinstance(transcript, Mapping):
            raise ValueError("P94 transcripts must be objects")
        if transcript.get("zero_side_effect_counters") != _ZERO_SIDE_EFFECT_COUNTERS:
            raise ValueError("P94 transcript must preserve zero side-effect counters")
        if _mapping(transcript.get("decision")).get("action_execution_allowed") is not False:
            raise ValueError("P94 transcript must forbid action execution")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else ()


__all__ = [
    "build_operator_transcript_demo",
    "render_operator_transcript_demo_markdown",
    "write_operator_transcript_demo_outputs",
]
