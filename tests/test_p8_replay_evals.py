from __future__ import annotations

from pathlib import Path

from app.services.replay_service import load_replay_scenarios
from scripts.run_replay_evals import run_replay_evals


def test_p8_replay_pack_has_40_operator_replacement_scenarios() -> None:
    scenarios = [scenario for scenario in load_replay_scenarios() if scenario.phase == "P8"]

    assert len(scenarios) >= 40
    required_classes = {
        "multi_service_partial_outage",
        "repeated_alert_storm",
        "deploy_provider_ambiguity",
        "stale_or_poisoned_memory",
        "runbook_mismatch",
        "rollback_worsens_blast_radius",
        "simulation_pass_post_check_fail",
        "safe_staging_auto_action",
        "unsafe_prod_block",
        "missing_logs_strong_metrics",
        "noisy_false_positive",
        "quiet_hours_night_autopilot_blocked",
    }
    observed_classes = {scenario.operator_replacement["scenario_class"] for scenario in scenarios}

    assert required_classes <= observed_classes
    for scenario in scenarios:
        contract = scenario.operator_replacement
        assert contract["expected_route"]
        assert contract["required_action"] in {"blocked", "allowed", "approval_required", "escalated"}
        assert isinstance(contract["missing_evidence"], list)
        assert contract["expected_human_question"]
        assert contract["reliability_score_band"] in {"low", "medium", "high"}


def test_p8_replay_summary_and_markdown_include_operator_replacement_pack(tmp_path: Path) -> None:
    output_json = tmp_path / "p8-replay.json"
    output_md = tmp_path / "p8-replay.md"

    summary = run_replay_evals(output_json=output_json, output_md=output_md)

    assert summary["p8_scenario_summary"]["total"] >= 40
    assert summary["p8_scenario_summary"]["missing_contract_fields"] == []
    assert summary["p8_scenario_summary"]["route_counts"]["escalated"] >= 1
    assert summary["p8_scenario_summary"]["action_counts"]["blocked"] >= 1
    assert summary["p8_scenario_summary"]["action_counts"]["allowed"] >= 1
    assert summary["p8_scenario_summary"]["score_band_counts"]["low"] >= 1
    assert summary["p8_scenario_summary"]["score_band_counts"]["medium"] >= 1
    assert summary["p8_scenario_summary"]["score_band_counts"]["high"] >= 1

    rendered = output_md.read_text(encoding="utf-8")
    assert "OpsCat P8 Operator-Replacement Scenario Summary" in rendered
    assert "P8 scenarios:" in rendered
