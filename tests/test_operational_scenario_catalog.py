from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.services.causal_remediation_benchmark import IsolatedFaultLab
from app.services.operational_scenario_catalog import (
    ADDITIONAL_OPERATIONAL_FAMILIES,
    build_comprehensive_operational_catalog,
    render_operational_matrix_markdown,
)

EXPECTED_ADDITIONAL_FAMILIES = {
    "memory_leak",
    "oom_kill",
    "cpu_throttling",
    "thread_pool_exhaustion",
    "file_descriptor_exhaustion",
    "disk_capacity",
    "disk_iops",
    "db_lock_contention",
    "db_replication_lag",
    "slow_query",
    "dns_resolution",
    "tls_expiry",
    "packet_loss",
    "clock_skew",
    "rate_limit",
    "quota_exhaustion",
    "dependency_brownout",
    "regional_partial_outage",
    "autoscaling_oscillation",
    "traffic_spike",
    "poison_message",
    "duplicate_processing",
    "batch_failure",
    "scheduler_missed_job",
    "config_drift",
    "feature_flag_drift",
    "secret_expiry",
    "data_corruption",
    "schema_mismatch",
    "cache_stampede",
    "retry_storm",
    "cascading_failure",
    "rollback_failure",
    "canary_regression",
    "cost_runaway",
    "webhook_delivery",
    "search_index_lag",
    "storage_corruption",
    "leader_election_churn",
    "service_discovery_stale",
}


def test_comprehensive_catalog_has_52_families_and_520_cases() -> None:
    cases = build_comprehensive_operational_catalog()

    assert len(ADDITIONAL_OPERATIONAL_FAMILIES) == 40
    assert {family.name for family in ADDITIONAL_OPERATIONAL_FAMILIES} == EXPECTED_ADDITIONAL_FAMILIES
    assert len(cases) == 520
    assert len({case.case_id for case in cases}) == 520
    assert len({case.family for case in cases}) == 52
    assert all(sum(case.family == family for case in cases) == 10 for family in {case.family for case in cases})
    assert Counter(case.split for case in cases) == {"development": 312, "validation": 104, "blind": 104}
    assert all(re.fullmatch(r"p(?:97|99)-[0-9a-f]{12}", case.case_id) for case in cases)


def test_additional_catalog_covers_all_required_failure_domains() -> None:
    domains = {family.domain for family in ADDITIONAL_OPERATIONAL_FAMILIES}

    assert {
        "resource",
        "storage",
        "database",
        "network",
        "dependency",
        "platform",
        "messaging",
        "scheduler",
        "configuration",
        "security",
        "data_integrity",
        "regional",
        "cost",
    }.issubset(domains)


def test_high_risk_families_expose_a_visible_approval_boundary() -> None:
    cases = build_comprehensive_operational_catalog()
    high_risk_families = {family.name for family in ADDITIONAL_OPERATIONAL_FAMILIES if family.human_required}
    visible_cases = [
        case
        for case in cases
        if case.family in high_risk_families and case.variant not in {"missing_telemetry"}
    ]

    assert high_risk_families
    assert visible_cases
    assert all("privileged_scope_required" in case.visible_evidence for case in visible_cases)


def test_every_new_obvious_runbook_causes_measured_recovery() -> None:
    cases = [case for case in build_comprehensive_operational_catalog() if case.case_id.startswith("p99-") and case.variant == "obvious"]

    assert len(cases) == 40
    with IsolatedFaultLab(sample_size=5) as lab:
        for case in cases:
            lab.reset(case, seed=17)
            before = lab.observe()
            for action in case.runbook_actions:
                lab.apply_action(action)
            after = lab.observe()
            durability = lab.observe()
            assert before.recovered is False, case.family
            assert after.utility > before.utility, case.family
            assert after.availability >= 0.8, case.family
            assert after.latency_ms <= 150, case.family
            assert after.backlog <= 10, case.family
            assert after.collateral_regressions == 0, case.family
            assert durability.utility >= after.utility - 0.1, case.family


def test_operational_matrix_cli_writes_bounded_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "p99.json"
    output_md = tmp_path / "p99.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_operational_scenario_matrix.py",
            "--max-cases",
            "20",
            "--seeds",
            "7",
            "--sample-size",
            "5",
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
    assert payload["summary"]["catalog_case_count"] == 520
    assert payload["summary"]["evaluated_case_count"] == 20
    assert payload["summary"]["catalog_family_count"] == 52
    assert payload["summary"]["family_count"] == 20
    assert payload["summary"]["execution_valid"] is True
    assert payload["safety"]["hard_gate_passed"] is True
    assert "Comprehensive Operational Failure Matrix" in markdown
    assert "520" in markdown
    assert render_operational_matrix_markdown(payload).startswith("# OpsCat Comprehensive Operational Failure Matrix")
    assert '"execution_valid": true' in completed.stdout.lower()
