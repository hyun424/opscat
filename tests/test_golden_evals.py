"""Golden scenario evals for deterministic OpsCat MVP behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_golden(name: str) -> dict[str, Any]:
    path = Path("evals/golden") / f"{name}.json"
    return json.loads(path.read_text())


def test_payment_bad_deploy_golden_file_is_complete() -> None:
    golden = _load_golden("payment_bad_deploy")
    assert golden["scenario"] == "payment_bad_deploy"
    assert golden["input_alert"]["service"] == "payment-api"
    assert golden["expected"]["top_cause_contains"]
    assert golden["expected"]["recommended_actions"]
    assert golden["expected"]["minimum_supporting_evidence"] >= 2


def test_payment_bad_deploy_eval_contract(client: Any) -> None:
    golden = _load_golden("payment_bad_deploy")
    created = client.post("/webhooks/alerts/mock", json=golden["input_alert"])
    assert created.status_code in {200, 201, 202}, created.text
    result = created.json()
    text = json.dumps(result).lower()

    assert golden["expected"]["top_cause_contains"].lower() in text
    assert any(action in text for action in golden["expected"]["recommended_actions"])

    evidence_ids = set()
    for action in result.get("actions", []):
        evidence_ids.update(action.get("evidence_ids", []))
    assert len(evidence_ids) >= golden["expected"]["minimum_supporting_evidence"]
