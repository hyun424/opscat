from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.proactive_risk_sentinel import (
    PreventiveActionPlanner,
    ProactiveRiskSentinel,
    RiskSignal,
    TrendWindow,
    load_proactive_fixtures,
    render_proactive_markdown,
)

FIXTURE_PATH = Path("evals/proactive/seed/risk_windows.json")


def test_load_proactive_fixtures_have_preincident_coverage() -> None:
    windows = load_proactive_fixtures(FIXTURE_PATH)
    risk_types = {window.risk_type for window in windows}

    assert len(windows) >= 12
    assert {
        "connection_pool_saturation",
        "disk_full_eta",
        "queue_sla_breach",
        "cache_eviction_db_overload",
        "error_budget_burn",
        "observability_gap",
        "false_positive_transient",
    }.issubset(risk_types)
    assert all(window.local_mock_only for window in windows)


def test_trend_window_detects_eta_and_signal_for_connection_pool() -> None:
    window = next(item for item in load_proactive_fixtures(FIXTURE_PATH) if item.id == "pre-db-pool-wait-rising")

    signal = RiskSignal.from_window(window)

    assert signal.risk_type == "connection_pool_saturation"
    assert signal.trend in {"rising", "saturation"}
    assert signal.baseline_ratio > 5
    assert signal.eta_minutes is not None
    assert 0 < signal.eta_minutes <= 45
    assert signal.confidence >= 0.7
    assert signal.evidence_ids


def test_sentinel_forecasts_risk_without_auto_remediation() -> None:
    result = ProactiveRiskSentinel().run(load_proactive_fixtures(FIXTURE_PATH), max_windows=8)
    payload = result.to_dict()

    assert payload["summary"]["window_count"] == 8
    assert payload["summary"]["forecast_count"] >= 6
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert payload["score"]["lead_time_minutes_min"] > 0
    assert payload["boundary"]["action_execution_enabled"] is False
    assert all(forecast["route"] in {"preventive_review", "blocked", "monitor"} for forecast in payload["forecasts"])


def test_preventive_action_planner_separates_readonly_from_approval_required() -> None:
    window = next(item for item in load_proactive_fixtures(FIXTURE_PATH) if item.id == "pre-db-pool-wait-rising")
    signal = RiskSignal.from_window(window)

    plan = PreventiveActionPlanner().plan(signal)
    payload = plan.to_dict()

    assert payload["auto_allowed_actions"]
    assert all(action["capability"] in {"read_only_diagnostic", "report", "notification_draft"} for action in payload["auto_allowed_actions"])
    assert any("approval_required" == action["route"] for action in payload["approval_required_actions"])
    assert payload["blocked_actions"]
    assert all(action["action_execution_enabled"] is False for action in payload["auto_allowed_actions"])


def test_proactive_markdown_and_cli_write_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "proactive.json"
    output_md = tmp_path / "proactive.md"

    subprocess.run(
        [
            "python",
            "scripts/run_proactive_risk_sentinel.py",
            "--fixtures",
            str(FIXTURE_PATH),
            "--max-windows",
            "6",
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
    assert payload["summary"]["window_count"] == 6
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert "# OpsCat Proactive Risk Sentinel" in markdown
    assert "no remediation execution" in markdown
    assert render_proactive_markdown(payload).startswith("# OpsCat Proactive Risk Sentinel")
