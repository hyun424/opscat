from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p177_policy import P177PolicyError, validate_final_decision
from app.services.p177_tools import P177ToolError, ToolBudget, ToolRegistry, ToolSpec
from app.services.p177_trace import (
    P177TraceError,
    append_trace_event,
    validate_trace_chain,
)


def _registry() -> ToolRegistry:
    return ToolRegistry(
        version="p177-test-registry",
        tools=[
            ToolSpec(
                tool_id="metrics.window",
                source_class="metrics",
                provider="p176_recorded",
                template="metrics:{episode_id}:{window}",
                freshness_bound_seconds=300,
                max_calls=2,
            ),
            ToolSpec(
                tool_id="logs.window",
                source_class="logs",
                provider="p176_recorded",
                template="logs:{episode_id}:{window}",
                freshness_bound_seconds=300,
                max_calls=1,
            ),
        ],
    )


def test_trace_chain_records_hypothesis_tool_evidence_contradiction_and_stop() -> None:
    registry = _registry()
    budget = ToolBudget(max_queries=3, max_tool_calls=3, max_time_ms=1_000, max_tokens=500)
    evidence = registry.execute(
        tool_id="metrics.window",
        params={"episode_id": "ep-1", "window": "pre"},
        observed_at="2026-07-18T00:00:00Z",
        received_at="2026-07-18T00:00:30Z",
        content={"cpu": "high", "service": "checkout"},
        budget=budget,
        elapsed_ms=50,
        tokens_used=20,
    )
    events: list[dict[str, Any]] = []
    for event_type, payload in (
        ("hypothesis", {"hypothesis_id": "h1", "statement": "checkout saturation"}),
        ("question", {"question_id": "q1", "text": "is checkout cpu high"}),
        ("tool_choice", {"tool_id": "metrics.window", "query": "checkout pre window"}),
        ("evidence_result", evidence),
        (
            "contradiction",
            {
                "contradiction_id": "c1",
                "kind": "source_conflict",
                "evidence_ids": [evidence["evidence_id"]],
                "description": "logs do not yet confirm cpu pressure",
                "severity": 0.4,
            },
        ),
        ("revision", {"hypothesis_id": "h1", "uncertainty": 0.35}),
        ("stop", {"stop_reason": "final_diagnosis", "cited_evidence_ids": [evidence["evidence_id"]]}),
    ):
        events.append(append_trace_event(previous=events[-1] if events else None, event_type=event_type, payload=payload))

    validate_trace_chain(events)
    assert events[-1]["previous_event_hash"] == events[-2]["event_hash"]

    tampered = deepcopy(events)
    tampered[2]["payload"]["tool_id"] = "unknown"
    with pytest.raises(P177TraceError, match="event_hash_invalid"):
        validate_trace_chain(tampered)


def test_registry_blocks_unknown_mutating_template_and_budget_exhaustion() -> None:
    with pytest.raises(P177ToolError, match="mutating_tool_forbidden"):
        ToolSpec(
            tool_id="kubectl.delete",
            source_class="metrics",
            provider="p176_recorded",
            template="kubectl delete pod {name}",
            freshness_bound_seconds=60,
            max_calls=1,
        )
    with pytest.raises(P177ToolError, match="free_form_template_forbidden"):
        ToolSpec(
            tool_id="logs.free",
            source_class="logs",
            provider="p176_recorded",
            template="https://example.invalid/{episode_id}",
            freshness_bound_seconds=60,
            max_calls=1,
        )

    registry = _registry()
    budget = ToolBudget(max_queries=1, max_tool_calls=1, max_time_ms=100, max_tokens=30)
    registry.execute(
        tool_id="metrics.window",
        params={"episode_id": "ep-1", "window": "pre"},
        observed_at="2026-07-18T00:00:00Z",
        received_at="2026-07-18T00:00:30Z",
        content={"signal": "one"},
        budget=budget,
        elapsed_ms=10,
        tokens_used=10,
    )
    with pytest.raises(P177ToolError, match="budget_exhausted"):
        registry.execute(
            tool_id="logs.window",
            params={"episode_id": "ep-1", "window": "pre"},
            observed_at="2026-07-18T00:00:00Z",
            received_at="2026-07-18T00:00:30Z",
            content={"signal": "two"},
            budget=budget,
            elapsed_ms=10,
            tokens_used=10,
        )
    with pytest.raises(P177ToolError, match="unknown_tool"):
        registry.execute(
            tool_id="shell.any",
            params={"episode_id": "ep-1"},
            observed_at="2026-07-18T00:00:00Z",
            received_at="2026-07-18T00:00:30Z",
            content={"signal": "bad"},
            budget=ToolBudget(max_queries=3, max_tool_calls=3, max_time_ms=100, max_tokens=30),
            elapsed_ms=10,
            tokens_used=10,
        )


def test_policy_rejects_missing_stale_forged_duplicate_single_source_and_unsafe_advice() -> None:
    registry = _registry()
    fresh = registry.execute(
        tool_id="metrics.window",
        params={"episode_id": "ep-1", "window": "pre"},
        observed_at="2026-07-18T00:00:00Z",
        received_at="2026-07-18T00:00:30Z",
        content={"signal": "metric"},
        budget=ToolBudget(max_queries=5, max_tool_calls=5, max_time_ms=1000, max_tokens=100),
        elapsed_ms=20,
        tokens_used=10,
    )
    log = registry.execute(
        tool_id="logs.window",
        params={"episode_id": "ep-1", "window": "pre"},
        observed_at="2026-07-18T00:01:00Z",
        received_at="2026-07-18T00:01:20Z",
        content={"signal": "log"},
        budget=ToolBudget(max_queries=5, max_tool_calls=5, max_time_ms=1000, max_tokens=100),
        elapsed_ms=20,
        tokens_used=10,
    )
    decision = {
        "decision_type": "diagnosis",
        "root_cause": "checkout_cpu_saturation",
        "cited_evidence_ids": [fresh["evidence_id"], log["evidence_id"]],
        "uncertainty": 0.2,
        "contradictions_considered": [
            {"contradiction_id": "c1", "kind": "source_conflict", "evidence_ids": [fresh["evidence_id"]], "severity": 0.3, "resolution": "weakened_confidence"}
        ],
        "advice": "escalate to human operator; no action execution",
    }

    result = validate_final_decision(decision, evidence_records=[fresh, log], registry=registry)
    assert result["citation_validity"] == 1.0
    assert result["decision_hash"] == stable_hash({key: value for key, value in result.items() if key != "decision_hash"})

    for mutation, error in (
        ({"cited_evidence_ids": [fresh["evidence_id"], "forged"]}, "unsupported_citation"),
        ({"cited_evidence_ids": [fresh["evidence_id"], fresh["evidence_id"]]}, "duplicate_citation"),
        ({"cited_evidence_ids": [fresh["evidence_id"]]}, "source_diversity_required"),
        ({"advice": "run kubectl delete pod in production"}, "unsafe_action_advice"),
        ({"contradictions_considered": []}, "contradictions_required"),
    ):
        bad = dict(decision)
        bad.update(mutation)
        with pytest.raises(P177PolicyError, match=error):
            validate_final_decision(bad, evidence_records=[fresh, log], registry=registry)

    stale = dict(fresh)
    stale["fresh"] = False
    with pytest.raises(P177PolicyError, match="stale_citation"):
        validate_final_decision(decision, evidence_records=[stale, log], registry=registry)
