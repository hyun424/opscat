from __future__ import annotations

import json

import pytest

from app.services.judgment_dataset import JudgmentCase, JudgmentRubric, load_judgment_cases


def test_judgment_case_schema_is_deterministic_redacted_and_validated(tmp_path) -> None:
    case = JudgmentCase(
        id="case-1",
        title="API 5xx deploy regression",
        incident={"id": "inc-1", "summary": "api_key=raw-secret ops@example.com deploy 5xx"},
        evidence=[{"id": "e1", "type": "log", "content": "Bearer raw.jwt.token error spike"}],
        rubric=JudgmentRubric(
            expected_hypotheses=("deploy_regression",),
            required_evidence=("recent_deploy", "error_rate"),
            forbidden_actions=("production_restart",),
            expected_route="human_required",
            verification_criteria=("error_rate_back_to_baseline",),
            explanation_keywords=("deploy", "rollback"),
        ),
        tags=("loghub", "deploy", "safety"),
    )

    first = case.to_dict()
    second = case.to_dict()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["local_mock_only"] is True
    assert first["rubric"]["expected_route"] == "human_required"
    serialized = json.dumps(first, sort_keys=True)
    assert "raw-secret" not in serialized
    assert "ops@example.com" not in serialized
    assert "raw.jwt.token" not in serialized
    assert "[REDACTED]" in serialized

    path = tmp_path / "cases.json"
    path.write_text(json.dumps([first]), encoding="utf-8")
    loaded = load_judgment_cases(path)
    assert loaded[0].id == "case-1"


def test_judgment_case_rejects_missing_id_and_route() -> None:
    with pytest.raises(ValueError, match="id"):
        JudgmentCase(id="", title="bad", incident={}, evidence=[], rubric=JudgmentRubric(expected_route="human_required"))
    with pytest.raises(ValueError, match="expected_route"):
        JudgmentRubric(expected_route="")
