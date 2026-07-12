from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS
from app.services.p125_shadow_resilience import (
    P125_AUTHORITY_COUNTERS,
    P125_INTERRUPTION_POINTS,
    P125_RECORD_FAMILIES,
    ShadowResilienceError,
    build_release_evidence,
    load_soak_profile,
    run_shadow_resilience,
    validate_shadow_resilience_report,
    zero_authority_counters,
)
from scripts.run_p125_shadow_resilience import main


def test_shadow_resilience_soak_accounts_for_all_records(tmp_path: Path) -> None:
    profile = load_soak_profile(Path("evals/p125/input/soak-profile.json"))
    report, ledger_lines = run_shadow_resilience(profile=profile, ledger_path=tmp_path / "ledger.jsonl")

    assert report["schema_version"] == "p125.resilience_report.v1"
    assert report["profile"]["event_count"] == 10000
    assert report["restart_matrix"]["point_count"] == 12
    assert {point["name"] for point in report["restart_matrix"]["points"]} == set(P125_INTERRUPTION_POINTS)
    assert len(ledger_lines) == 10000
    assert (tmp_path / "ledger.jsonl").is_file()

    for family in P125_RECORD_FAMILIES:
        counts = cast(dict[str, Any], report["durable_record_families"][family])
        assert counts["expected"] == 10000
        assert counts["committed"] == 10000
        assert counts["recovered"] == 10000
        assert counts["lost"] == 0
        assert counts["duplicated"] == 0
        assert counts["family_hash"].startswith("sha256:")

    assert report["loss_duplicate_summary"]["total_lost"] == 0
    assert report["loss_duplicate_summary"]["total_duplicated"] == 0
    assert report["deterministic_resume_rate"] == 1.0
    assert report["resource_gates"]["passed"] is True
    assert report["quality_gate"]["p124_preserved"] is True
    assert all(value == 0 for value in report["authority_counters"].values())
    assert validate_shadow_resilience_report(report, ledger_path=tmp_path / "ledger.jsonl") is True


def test_shadow_resilience_rejects_missing_crash_point(tmp_path: Path) -> None:
    profile = load_soak_profile(Path("evals/p125/input/soak-profile.json"))
    broken = dict(profile)
    broken["interruption_points"] = list(P125_INTERRUPTION_POINTS[:-1])
    with pytest.raises(ShadowResilienceError, match="interruption_points_mismatch"):
        run_shadow_resilience(profile=broken, ledger_path=tmp_path / "ledger.jsonl")


def test_shadow_resilience_runner_writes_atomic_outputs(tmp_path: Path) -> None:
    output = tmp_path / "resilience-report.json"
    ledger = tmp_path / "resilience-ledger.jsonl"
    evidence = tmp_path / "release-evidence.json"

    main(
        [
            "--profile",
            "evals/p125/input/soak-profile.json",
            "--output",
            str(output),
            "--ledger",
            str(ledger),
            "--release-evidence",
            str(evidence),
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    release = json.loads(evidence.read_text(encoding="utf-8"))
    assert ledger.read_text(encoding="utf-8").count("\n") == 10000
    assert report["report_hash"].startswith("sha256:")
    assert release["schema_version"] == "p125.release_evidence.v1"
    assert release["release_status"] == "ready"
    assert release["artifact_hashes"]["report_hash"] == report["report_hash"]
    assert release["gates"]["ready"] is True
    assert release["gates"]["authority_counters_zero"] is True
    assert set(release["authority"]["counters"]) == set(P121_AUTHORITY_COUNTER_KEYS)
    assert all(type(value) is int and value == 0 for value in release["authority"]["counters"].values())
    assert release["authority"]["p125_report_counters"] == report["authority_counters"]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    ("name", "counters"),
    [
        ("empty", {}),
        ("partial", {key: 0 for key in P125_AUTHORITY_COUNTERS[:-1]}),
        ("unknown", {**zero_authority_counters(), "unknown_counter": 0}),
        ("nonzero", {**zero_authority_counters(), P125_AUTHORITY_COUNTERS[0]: 1}),
        ("bool", {**zero_authority_counters(), P125_AUTHORITY_COUNTERS[0]: False}),
    ],
)
def test_shadow_resilience_rejects_non_exact_p125_authority_counters(tmp_path: Path, name: str, counters: dict[str, Any]) -> None:
    report = _valid_report()
    report["authority_counters"] = counters
    report["report_hash"] = f"sha256:{name}"
    report["atomic_evidence_hash"] = f"sha256:atomic-{name}"
    report_path = tmp_path / f"{name}-report.json"
    ledger_path = tmp_path / f"{name}-ledger.jsonl"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    ledger_path.write_text("", encoding="utf-8")

    assert validate_shadow_resilience_report(report) is False

    release = build_release_evidence(report, report_path=report_path, ledger_path=ledger_path)
    assert release["gates"]["ready"] is False
    assert release["gates"]["authority_counters_zero"] is False
    assert release["authority"]["exact_zero_runtime_authority"] is False
    assert release["authority"]["p125_report_counters"] == counters


def _valid_report() -> dict[str, Any]:
    event_count = 10_000
    return {
        "schema_version": "p125.resilience_report.v1",
        "profile": {"event_count": event_count},
        "restart_matrix": {
            "point_count": len(P125_INTERRUPTION_POINTS),
            "points": [{"name": name} for name in P125_INTERRUPTION_POINTS],
        },
        "durable_record_families": {
            family: {
                "expected": event_count,
                "committed": event_count,
                "recovered": event_count,
                "lost": 0,
                "duplicated": 0,
            }
            for family in P125_RECORD_FAMILIES
        },
        "loss_duplicate_summary": {"total_lost": 0, "total_duplicated": 0},
        "deterministic_resume_rate": 1.0,
        "resource_gates": {"passed": True},
        "authority_counters": zero_authority_counters(),
    }
