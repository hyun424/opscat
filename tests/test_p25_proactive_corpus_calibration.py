from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from app.services.proactive_risk_sentinel import (
    ProactiveRiskSentinel,
    evaluate_proactive_calibration,
    load_proactive_fixtures,
    render_proactive_calibration_markdown,
)

FIXTURE_PATH = Path("evals/proactive/seed/risk_windows.json")
REQUIRED_RISK_TYPES = {
    "connection_pool_saturation",
    "disk_full_eta",
    "queue_sla_breach",
    "cache_eviction_db_overload",
    "error_budget_burn",
    "observability_gap",
    "false_positive_transient",
    "slow_query_risk",
    "lock_wait_risk",
    "db_max_connections_risk",
    "memory_oom_eta",
    "certificate_expiry_risk",
    "replica_lag_read_risk",
    "alert_noise_risk",
    "consumer_lag_risk",
    "dead_letter_growth_risk",
    "provider_rate_limit_risk",
    "dns_failure_risk",
    "tls_handshake_risk",
    "bot_traffic_risk",
    "canary_regression_risk",
    "feature_flag_degradation_risk",
    "schema_drift_risk",
    "secret_leak_risk",
    "prompt_injection_risk",
    "metrics_cardinality_risk",
    "trace_drop_risk",
    "log_drop_risk",
    "data_freshness_risk",
    "duplicate_events_risk",
}


def test_proactive_fixture_corpus_has_operator_grade_size_taxonomy_and_expected_outcomes() -> None:
    windows = load_proactive_fixtures(FIXTURE_PATH)
    risk_types = {window.risk_type for window in windows}
    ids = [window.id for window in windows]

    assert len(windows) >= 100
    assert len(ids) == len(set(ids))
    assert len(risk_types) >= 30
    assert REQUIRED_RISK_TYPES.issubset(risk_types)
    for window in windows:
        assert window.local_mock_only is True
        assert window.evidence
        assert len(window.values) >= 5
        assert window.expected is not None
        assert window.expected.route in {"preventive_review", "monitor", "blocked"}
        assert window.expected.eta_min_minutes <= window.expected.eta_max_minutes
        assert window.expected.confidence_min >= 0.0
        assert "read_only_diagnostic" in window.expected.auto_capabilities
        assert "report" in window.expected.auto_capabilities
        assert window.expected.blocked_capabilities


def test_proactive_calibration_scores_routes_eta_confidence_and_action_safety() -> None:
    windows = load_proactive_fixtures(FIXTURE_PATH)
    result = ProactiveRiskSentinel().run(windows)

    report = evaluate_proactive_calibration(result)
    payload = report.to_dict()

    assert payload["summary"]["window_count"] >= 100
    assert payload["summary"]["risk_type_count"] >= 30
    assert payload["passed"] is True
    assert payload["score"]["route_mismatch_count"] == 0
    assert payload["score"]["eta_out_of_range_count"] == 0
    assert payload["score"]["confidence_below_floor_count"] == 0
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert payload["score"]["missing_expected_count"] == 0


def test_false_positive_and_blocked_routes_are_calibrated() -> None:
    windows = load_proactive_fixtures(FIXTURE_PATH)
    result = ProactiveRiskSentinel().run(windows)
    report = evaluate_proactive_calibration(result).to_dict()
    routes = Counter(item["actual_route"] for item in report["items"])
    expected_routes = Counter(item["expected_route"] for item in report["items"])

    assert routes["monitor"] >= 8
    assert routes["blocked"] >= 5
    assert routes["preventive_review"] >= 80
    assert routes == expected_routes


def test_proactive_calibration_markdown_and_cli_write_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "calibration.json"
    output_md = tmp_path / "calibration.md"

    subprocess.run(
        [
            "python",
            "scripts/run_proactive_calibration.py",
            "--fixtures",
            str(FIXTURE_PATH),
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
    assert payload["passed"] is True
    assert payload["summary"]["window_count"] >= 100
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert "# OpsCat Proactive Calibration Report" in markdown
    assert "risk_type_count" in markdown
    assert "no remediation execution" in markdown
    assert render_proactive_calibration_markdown(payload).startswith("# OpsCat Proactive Calibration Report")
