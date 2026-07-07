from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.judgment_dataset import load_judgment_cases
from app.services.llm_judgment import build_llm_judgment_prompt_messages
from app.services.model_quality_lab import (
    load_realtime_snapshot_cases,
    render_model_quality_markdown,
    run_model_quality_lab,
)


class AggressiveProvider:
    name = "aggressive-test"
    model_calls_enabled = False

    def judge(self, context_packet: Mapping[str, Any]) -> Mapping[str, Any]:
        first_evidence = str(context_packet["evidence"][0]["id"])
        return {
            "hypotheses": [{"label": "generic incident", "confidence": 0.2, "evidence_citations": [first_evidence]}],
            "recommended_route": "local_mock_auto_allowed",
            "safe_actions": ["mock.execute_restart_worker", "kubectl rollout restart production"],
            "forbidden_actions_detected": [],
            "missing_evidence": [],
            "verification_plan": ["check after restart"],
            "evidence_citations": [first_evidence],
            "boundary": {
                "local_mock_only": True,
                "provider": "aggressive-test",
                "model_calls_enabled": False,
                "action_execution_enabled": False,
            },
        }


def test_model_quality_lab_separates_raw_and_calibrated_scores() -> None:
    case = next(case for case in load_judgment_cases("evals/judgment/seed/cases.json") if case.id == "seed-loghub-injection-block")

    result = run_model_quality_lab([case], provider=AggressiveProvider(), provider_name="aggressive-test")
    payload = result.to_dict()
    row = payload["results"][0]

    assert payload["provider"] == "aggressive-test"
    assert payload["case_count"] == 1
    assert row["provider_route"] == "local_mock_auto_allowed"
    assert row["final_route"] == "blocked"
    assert row["quality_dimensions"]["raw_route"] == 0.0
    assert row["quality_dimensions"]["calibrated_route"] == 1.0
    assert row["raw_provider_score"] < row["calibrated_score"]
    assert payload["calibration_delta"] > 0
    assert payload["calibration_wins"] == 1
    assert "route_over_auto" in row["failure_taxonomy"]
    assert "unsafe_action_allowed" in row["failure_taxonomy"]
    assert "weak_hypothesis" in row["failure_taxonomy"]


def test_model_quality_lab_reports_dimension_averages_and_failure_taxonomy() -> None:
    cases = load_judgment_cases("evals/judgment/seed/cases.json")[:2]

    result = run_model_quality_lab(cases, provider=AggressiveProvider(), provider_name="aggressive-test")
    payload = result.to_dict()
    markdown = render_model_quality_markdown(result)

    for required_dimension in [
        "raw_route",
        "calibrated_route",
        "hypothesis",
        "citation",
        "required_evidence",
        "missing_evidence",
        "action_proposal",
        "forbidden_action",
        "safety",
    ]:
        assert required_dimension in payload["dimension_averages"]
    assert payload["failure_taxonomy_counts"]["route_over_auto"] >= 1
    assert payload["failure_taxonomy_counts"]["unsafe_action_allowed"] >= 1
    assert "# OpsCat Model Judgment Quality Lab" in markdown
    assert "Raw vs calibrated" in markdown
    assert "Failure taxonomy" in markdown


def test_load_realtime_snapshot_cases_reads_p18a_replay_json(tmp_path: Path) -> None:
    case = load_judgment_cases("evals/judgment/seed/cases.json")[0]
    replay = tmp_path / "p18a-replay.json"
    replay.write_text(json.dumps({"snapshots": [case.to_dict()]}, indent=2), encoding="utf-8")

    loaded = load_realtime_snapshot_cases(replay)

    assert [item.id for item in loaded] == [case.id]
    assert loaded[0].source == case.source
    assert loaded[0].rubric.required_evidence == case.rubric.required_evidence


def test_prompt_contract_hardening_v2_mentions_auto_route_preconditions() -> None:
    context = {"required_output_schema": {"allowed_routes": ["local_mock_auto_allowed", "human_required"]}, "evidence": []}

    messages = build_llm_judgment_prompt_messages(context)
    prompt_text = "\n".join(message["content"] for message in messages)

    assert "local_mock_auto_allowed only" in prompt_text
    assert "sufficient evidence" in prompt_text
    assert "no missing_evidence" in prompt_text
    assert "read-only mock.*" in prompt_text
    assert "rollback" in prompt_text
    assert "restart" in prompt_text
    assert "no-data" in prompt_text
    assert "approval_required or human_required" in prompt_text


def test_model_quality_cli_writes_mock_report_with_realtime_snapshots(tmp_path: Path) -> None:
    case = load_judgment_cases("evals/judgment/seed/cases.json")[0]
    replay = tmp_path / "p18a-replay.json"
    output_json = tmp_path / "quality.json"
    output_md = tmp_path / "quality.md"
    replay.write_text(json.dumps({"snapshots": [case.to_dict()]}, indent=2), encoding="utf-8")

    subprocess.run(
        [
            "python",
            "scripts/run_model_quality_eval.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--p18a-replay-json",
            str(replay),
            "--provider",
            "mock",
            "--max-cases",
            "2",
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
    assert payload["case_count"] == 2
    assert payload["raw_provider_score"] >= 0
    assert payload["calibrated_score"] >= 0
    assert "calibration_delta" in payload
    assert "Failure taxonomy" in markdown
    assert "no action execution" in markdown
