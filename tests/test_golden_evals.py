"""Golden scenario evals for deterministic OpsCat MVP behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

GOLDEN_DIR = Path("evals/golden")
REQUIRED_SCENARIOS = {
    "payment_bad_deploy",
    "external_api_timeout",
    "worker_queue_backlog",
    "duplicate_alert_storm",
    "prompt_injection_log",
    "secret_bearing_alert",
    "protected_auth_incident",
    "missing_runbook_context",
    "verification_failure",
    "low_confidence_ambiguous",
}


def _load_golden(name: str) -> dict[str, Any]:
    path = GOLDEN_DIR / f"{name}.json"
    return json.loads(path.read_text())


def _golden_names() -> list[str]:
    return sorted(path.stem for path in GOLDEN_DIR.glob("*.json"))


def test_portfolio_golden_scenarios_exist() -> None:
    names = set(_golden_names())
    assert len(names) >= 20
    assert REQUIRED_SCENARIOS.issubset(names)


@pytest.mark.parametrize("name", _golden_names())
def test_golden_file_is_complete(name: str) -> None:
    golden = _load_golden(name)
    expected = golden["expected"]

    assert golden["scenario"] == name
    assert golden["input_alert"]["scenario"] == name
    assert golden["input_alert"]["service"]
    assert expected["top_cause_contains"]
    assert expected["recommended_actions"]
    assert expected["minimum_supporting_evidence"] >= 2
    assert expected["required_policy_decision"] in {"ALLOW", "REQUIRE_APPROVAL", "DENY", "ESCALATE"}
    assert expected["required_post_checks"]
    assert expected["expected_route"] in {"auto_allowed", "waiting_approval", "escalated", "resolved_after_approval", "escalated_after_approval"}
    assert isinstance(expected["must_escalate"], bool)
    assert isinstance(expected["must_redact"], bool)
    assert golden["category"]
    assert golden["safety_focus"]


@pytest.mark.parametrize("name", _golden_names())
def test_golden_eval_contract(client: Any, name: str) -> None:
    golden = _load_golden(name)
    created = client.post("/webhooks/alerts/mock?process_now=true", json=golden["input_alert"])
    assert created.status_code in {200, 201, 202}, created.text
    result = created.json()
    expected = golden["expected"]
    if expected["expected_route"] in {"resolved_after_approval", "escalated_after_approval"}:
        action_id = result["actions"][0]["id"]
        decided = client.post(
            f"/approvals/{action_id}",
            json={"decision": "approve", "actor": "eval-test", "reason": f"approve {name}"},
        )
        assert decided.status_code == 200, decided.text
        result = decided.json()["incident"]
    text = json.dumps(result).lower()

    assert expected["top_cause_contains"].lower() in text
    assert any(action in text for action in expected["recommended_actions"])
    assert expected["required_policy_decision"].lower() in text

    evidence_ids = set()
    for action in result.get("actions", []):
        evidence_ids.update(action.get("evidence_ids", []))
        assert set(expected["required_post_checks"]).intersection(set(action.get("post_checks", [])))
    assert len(evidence_ids) >= expected["minimum_supporting_evidence"]
