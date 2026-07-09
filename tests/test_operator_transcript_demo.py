from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.operator_transcript_demo import (
    build_operator_transcript_demo,
    render_operator_transcript_demo_markdown,
)

FIXTURE = Path("evals/actions/p94_operator_transcript_demo.json")
ZERO_COUNTERS = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "external_model_call_count": 0,
    "real_remediation_execution_count": 0,
}


def _demo() -> dict[str, Any]:
    return build_operator_transcript_demo(FIXTURE)


def test_operator_transcript_demo_exposes_required_structured_fields() -> None:
    payload = _demo()

    assert payload["demo_id"] == "p94-operator-transcript-demo"
    assert payload["title"] == "OpsCat Operator Transcript Demo / Human-like Incident Response Walkthrough"
    assert payload["summary"] == {
        "scenarios": 4,
        "transcript_steps": 40,
        "hypotheses": 12,
        "executions": 0,
        "recovery_proven": 1,
        "blocked": 2,
        "human_gated": 1,
        "passed": True,
    }

    for transcript in payload["transcripts"]:
        for required in [
            "transcript_id",
            "scenario_id",
            "title",
            "operator_goal",
            "transcript_steps",
            "hypotheses",
            "tool_plan",
            "decision",
            "verification",
            "report_summary",
            "safety_boundaries",
            "forbidden_claims",
            "zero_side_effect_counters",
        ]:
            assert required in transcript
        assert len(transcript["transcript_steps"]) >= 10
        assert len(transcript["hypotheses"]) >= 3
        assert transcript["zero_side_effect_counters"] == ZERO_COUNTERS
        assert transcript["decision"]["action_execution_allowed"] is False
        assert transcript["tool_plan"]["read_only"] is True


def test_scenarios_cover_recovery_human_gate_and_blocked_safety_routes() -> None:
    payload = _demo()
    by_id = {item["scenario_id"]: item for item in payload["transcripts"]}

    assert set(by_id) == {
        "payment_deploy_regression",
        "db_connection_pool_saturation",
        "noisy_metric_spike_missing_evidence",
        "prompt_injection_like_log_content",
    }
    assert by_id["payment_deploy_regression"]["decision"]["recommended_route"] == "safe_rollback_pr_draft"
    assert by_id["payment_deploy_regression"]["verification"]["observed_outcome"] == "local_mock_recovery_proven"
    assert by_id["payment_deploy_regression"]["verification"]["recovery_proven"] is True
    assert by_id["db_connection_pool_saturation"]["decision"]["recommended_route"] == (
        "human_gated_scale_connection_pool_handoff"
    )
    assert by_id["db_connection_pool_saturation"]["verification"]["observed_outcome"] == "recovery_not_proven"
    assert by_id["noisy_metric_spike_missing_evidence"]["decision"]["recommended_route"] == (
        "blocked_more_evidence_needed"
    )
    assert by_id["prompt_injection_like_log_content"]["decision"]["recommended_route"] == (
        "blocked_safety_guardrail"
    )


def test_transcript_steps_read_like_evidence_grounded_incident_response() -> None:
    payload = _demo()
    required_phases = {
        "observe",
        "suspect",
        "choose_tools",
        "inspect_evidence",
        "compare_hypotheses",
        "decide_safely",
        "draft_handoff",
        "verify",
        "report",
        "improve",
    }

    for transcript in payload["transcripts"]:
        phases = {step["phase"] for step in transcript["transcript_steps"]}
        assert required_phases <= phases
        for step in transcript["transcript_steps"]:
            assert step["step_id"].startswith("step-")
            assert step["observation"]
            assert step["reasoning_summary"]
            assert step["tool_or_evidence_refs"]
            assert step["confidence_delta"] in {"increase", "decrease", "unchanged", "blocked"}
            assert step["safety_gate"] in {"read_only", "draft_only", "human_approval_required", "blocked"}
            assert step["human_readable_line"]


def test_hypotheses_and_tool_plan_preserve_missing_evidence_and_skipped_tools() -> None:
    payload = _demo()

    for transcript in payload["transcripts"]:
        for hypothesis in transcript["hypotheses"]:
            for required in [
                "evidence_for",
                "evidence_against",
                "confidence",
                "missing_evidence",
                "disposition",
            ]:
                assert required in hypothesis
            assert 0.0 <= hypothesis["confidence"] <= 1.0
        assert transcript["tool_plan"]["selected_tools"]
        assert transcript["tool_plan"]["skipped_tools"]
        assert all(item["reason"] for item in transcript["tool_plan"]["skipped_tools"])


def test_safety_boundaries_and_forbidden_claims_are_explicit() -> None:
    payload = _demo()
    text = json.dumps(payload, sort_keys=True)

    for required_boundary in [
        "local/mock only",
        "no auth work",
        "no live APIs",
        "no credentials",
        "no network",
        "no production mutation",
        "no real remediation/action execution",
        "no external model/API calls",
    ]:
        assert required_boundary in payload["safety_boundaries"]
    for forbidden in [
        "production_autonomy",
        "executed_rollback",
        "executed_scale_up",
        "live_provider_verified_recovery",
        "credentialed_operation",
    ]:
        assert forbidden in payload["forbidden_claims"]
    assert "production autonomy approved" not in text
    assert "executed rollback" not in text


def test_markdown_renderer_is_reviewer_friendly_and_bounded() -> None:
    payload = _demo()
    markdown = render_operator_transcript_demo_markdown(payload)

    assert markdown.startswith("# OpsCat Operator Transcript Demo")
    assert "## Why this is the best quick reviewer demo" in markdown
    assert "agentic reasoning with evidence but no production action" in markdown
    assert "## Payment deploy regression" in markdown
    assert "safe rollback PR draft" in markdown
    assert "executions=0" in markdown
    assert "not production autonomy" in markdown


def test_cli_smoke_outputs_required_count_style_line(tmp_path: Path) -> None:
    output_json = tmp_path / "p94.json"
    output_md = tmp_path / "p94.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_operator_transcript_demo.py",
            "--input",
            str(FIXTURE),
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

    assert (
        "scenarios=4 transcript_steps>=40 hypotheses>=12 executions=0 "
        "recovery_proven=1 blocked=2 human_gated=1"
    ) in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Operator Transcript Demo" in markdown
