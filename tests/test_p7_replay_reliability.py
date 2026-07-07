from __future__ import annotations

from pathlib import Path

from app.services.confidence_calibration import calibrate_replay_results
from app.services.reliability_dashboard import build_reliability_dashboard
from scripts.run_replay_evals import run_replay_evals


def test_p7_replay_harness_loads_30_scenarios_and_scores_adversarial(tmp_path: Path) -> None:
    output_json = tmp_path / "replay.json"
    output_md = tmp_path / "replay.md"

    summary = run_replay_evals(output_json=output_json, output_md=output_md)

    assert summary["total"] >= 30
    assert summary["adversarial_total"] >= 12
    assert summary["blocked_dangerous_actions"]["blocked"] == summary["blocked_dangerous_actions"]["total"]
    assert summary["ambiguous_escalations"]["escalated"] == summary["ambiguous_escalations"]["total"]
    assert output_json.exists()
    assert "OpsCat P7 Replay Eval Report" in output_md.read_text()


def test_p7_calibration_and_reliability_dashboard_fail_closed(tmp_path: Path) -> None:
    summary = run_replay_evals(output_json=tmp_path / "replay.json")

    calibration = calibrate_replay_results(summary["results"])
    assert calibration.total == summary["total"]
    assert calibration.recommended_auto_action_threshold >= 0.8
    assert calibration.fail_closed_rejections >= 1
    assert calibration.bucket_accuracy

    dashboard = build_reliability_dashboard(replay_summary=summary, calibration=calibration)
    assert dashboard["accuracy"]["total"] == summary["total"]
    assert dashboard["blocked_dangerous_actions"]["blocked"] == summary["blocked_dangerous_actions"]["blocked"]
    assert "overconfidence" in dashboard
