from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.closed_loop_response import (
    execute_read_only_evidence_plan,
    render_closed_loop_markdown,
    run_closed_loop_response,
)
from app.services.judgment_dataset import JudgmentCase, JudgmentRubric, load_judgment_cases


class EvidenceSensitiveProvider:
    name = "evidence-sensitive"
    model_calls_enabled = False

    def judge(self, context_packet: Mapping[str, Any]) -> Mapping[str, Any]:
        evidence_ids = [str(item.get("id")) for item in context_packet.get("evidence", []) if isinstance(item, Mapping)]
        has_fetched_context = any(item.startswith("fetched:") for item in evidence_ids)
        citation = evidence_ids[0] if evidence_ids else "missing"
        if has_fetched_context:
            fetched = next(item for item in evidence_ids if item.startswith("fetched:"))
            return {
                "hypotheses": [{"label": "metric anomaly needs human review", "confidence": 0.78, "evidence_citations": [citation, fetched]}],
                "recommended_route": "human_required",
                "safe_actions": ["mock.query_metrics"],
                "forbidden_actions_detected": ["production_restart"],
                "missing_evidence": [],
                "verification_plan": ["review fetched metric and service health context"],
                "evidence_citations": [citation, fetched],
                "boundary": {
                    "local_mock_only": True,
                    "provider": self.name,
                    "model_calls_enabled": False,
                    "action_execution_enabled": False,
                },
            }
        return {
            "hypotheses": [{"label": "metric anomaly", "confidence": 0.5, "evidence_citations": [citation]}],
            "recommended_route": "local_mock_auto_allowed",
            "safe_actions": ["mock.execute_restart_worker", "kubectl rollout restart production"],
            "forbidden_actions_detected": [],
            "missing_evidence": [],
            "verification_plan": ["restart and see if it recovers"],
            "evidence_citations": [citation],
            "boundary": {
                "local_mock_only": True,
                "provider": self.name,
                "model_calls_enabled": False,
                "action_execution_enabled": False,
            },
        }


def _metric_no_data_case() -> JudgmentCase:
    return JudgmentCase(
        id="p20-no-data",
        title="Metric no-data should fetch read-only context",
        source="unit-test",
        incident={
            "id": "p20-no-data",
            "service": "payment-api",
            "environment": "prod-mock",
            "severity": "high",
            "summary": "payment metrics have no data and timeout errors are ambiguous",
            "root_cause_candidate": "metric anomaly",
            "confidence": 0.55,
        },
        evidence=[
            {
                "id": "metric:window",
                "type": "metric",
                "source": "unit",
                "content": "payment_success_rate no_data for 10m",
                "metadata": {"metric": "payment_success_rate"},
            }
        ],
        rubric=JudgmentRubric(
            expected_route="human_required",
            expected_hypotheses=("metric anomaly",),
            required_evidence=("metric:window",),
            forbidden_actions=("production_restart", "kubectl"),
            verification_criteria=("fetch_read_only_context",),
            explanation_keywords=("no data", "human review"),
        ),
        tags=("p20", "no_data", "metric"),
    )


def test_closed_loop_fetches_missing_evidence_rejudges_and_preserves_no_execution() -> None:
    result = run_closed_loop_response(_metric_no_data_case(), provider=EvidenceSensitiveProvider())
    payload = result.to_dict()

    assert payload["case_id"] == "p20-no-data"
    assert payload["initial_judgment"]["provider_route"] == "local_mock_auto_allowed"
    assert payload["revised_judgment"]["final_route"] == "human_required"
    assert payload["score_delta"]["raw_provider_score_delta"] >= 0
    assert payload["fetched_evidence"]
    assert all(item["id"].startswith("fetched:mock.") for item in payload["fetched_evidence"])
    assert payload["final_decision"]["route"] == "human_required"
    assert payload["boundary"]["action_execution_enabled"] is False
    assert payload["executed_actions"] == []
    assert [step["step"] for step in payload["trace"]] == [
        "observe",
        "initial_judgment",
        "evidence_gap",
        "evidence_fetch",
        "revised_judgment",
        "action_proposal",
        "simulation",
        "final_decision",
    ]


def test_read_only_evidence_executor_blocks_mutating_or_unknown_tools() -> None:
    safe = execute_read_only_evidence_plan(
        case_id="case-1",
        tools=["mock.query_metrics", "mock.get_service_health"],
        reason="need more context",
    )
    blocked = execute_read_only_evidence_plan(
        case_id="case-1",
        tools=["mock.query_metrics", "mock.execute_restart_worker", "kubectl.restart", "unknown.tool"],
        reason="bad plan",
    )

    assert [item["id"] for item in safe] == ["fetched:mock.query_metrics", "fetched:mock.get_service_health"]
    assert [item["id"] for item in blocked] == ["fetched:mock.query_metrics"]
    assert all("restart" not in item["content"].lower() for item in blocked)


def test_closed_loop_simulates_proposed_actions_before_final_route() -> None:
    result = run_closed_loop_response(_metric_no_data_case(), provider=EvidenceSensitiveProvider())
    payload = result.to_dict()

    assert payload["proposed_actions"]
    assert payload["simulations"]
    assert {item["action_type"] for item in payload["simulations"]} == {item["action_type"] for item in payload["proposed_actions"]}
    assert all(item["status"] in {"pass", "blocked", "escalate"} for item in payload["simulations"])
    assert "Closed-loop" in render_closed_loop_markdown(result)


def test_closed_loop_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    case = load_judgment_cases("evals/judgment/seed/cases.json")[0]
    case_file = tmp_path / "cases.json"
    output_json = tmp_path / "loop.json"
    output_md = tmp_path / "loop.md"
    case_file.write_text(json.dumps([case.to_dict()], indent=2), encoding="utf-8")

    subprocess.run(
        [
            "python",
            "scripts/run_closed_loop_response.py",
            "--cases",
            str(case_file),
            "--case-id",
            case.id,
            "--provider",
            "mock",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["case_id"] == case.id
    assert payload["trace"]
    assert payload["boundary"]["action_execution_enabled"] is False
    assert "# OpsCat Closed-loop Incident Response" in markdown
    assert "no action execution" in markdown
