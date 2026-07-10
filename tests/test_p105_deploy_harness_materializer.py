from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

DEPLOY_SCRIPT = Path("scripts/run_p105_deploy_canary_harness.py")
VERIFY_SCRIPT = Path("scripts/verify_p105_source_expansion_artifacts.py")


def _require_deploy_script() -> None:
    if not DEPLOY_SCRIPT.exists():
        pytest.fail("P105-027 RED: missing scripts/run_p105_deploy_canary_harness.py loopback deploy canary harness.", pytrace=False)


def _run_deploy(output_dir: Path, *, fault_tick: int = 300) -> subprocess.CompletedProcess[str]:
    _require_deploy_script()
    return subprocess.run(
        [
            sys.executable,
            str(DEPLOY_SCRIPT),
            "--host",
            "127.0.0.1",
            "--seed",
            "105027",
            "--ticks",
            "1200",
            "--tick-seconds",
            "1",
            "--requests-per-tick",
            "10",
            "--fault-tick",
            str(fault_tick),
            "--output-dir",
            str(output_dir),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:23:20Z",
            "--expect-rollback-trigger-tick",
            "369",
            "--expect-rollback-observed-tick",
            "370",
            "--expect-no-production-authority",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_deploy_harness_outputs_canary_telemetry_private_ledger_rollback_evidence_and_manifest(tmp_path: Path) -> None:
    output = tmp_path / "deploy"
    completed = _run_deploy(output)

    assert completed.returncode == 0, completed.stderr
    expected = {
        "p105-deploy-public-telemetry.jsonl",
        "p105-deploy-private-injection-ledger.json",
        "p105-deploy-pre-label-partitions.json",
        "p105-deploy-rollback-evidence.json",
        "p105-deploy-coverage.json",
        "p105-deploy-harness-manifest.json",
        "p105-deploy-provenance-hashes.json",
    }
    assert expected <= {path.name for path in output.iterdir()}
    first_row = json.loads((output / "p105-deploy-public-telemetry.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert {"cohort", "public_version_hash", "status_code", "latency_bucket_ms", "rolling_error_rate", "rollback_state"} <= set(first_row)
    assert "injected_config_bytes" not in first_row
    ledger = json.loads((output / "p105-deploy-private-injection-ledger.json").read_text(encoding="utf-8"))
    assert ledger["label_join_phase"] == "after_sampling_and_partition"
    rollback = json.loads((output / "p105-deploy-rollback-evidence.json").read_text(encoding="utf-8"))
    assert rollback["trigger_tick"] == 369
    assert rollback["rollback_observed_tick"] == 370
    assert rollback["grants_p106_or_p107_authority"] is False


def test_deploy_harness_fixed_program_has_no_cloud_pr_credentials_or_production_mutation(tmp_path: Path) -> None:
    output = tmp_path / "deploy"
    completed = _run_deploy(output)

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((output / "p105-deploy-harness-manifest.json").read_text(encoding="utf-8"))
    assert manifest["program_version"] == "p105.deploy.canary.v1"
    assert manifest["seed"] == 105027
    assert manifest["host"] == "127.0.0.1"
    assert manifest["schedule"]["baseline_slots"] == [0, 7]
    assert manifest["schedule"]["canary_slots"] == [8, 9]
    assert manifest["schedule"]["fault_tick"] == 300
    assert manifest["authority"] == {
        "cloud_api_calls": False,
        "production_deploy_tooling": False,
        "real_pr_creation": False,
        "credentials_read": False,
        "production_mutation": False,
    }


def test_deploy_harness_reruns_are_byte_identical_and_tamper_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert _run_deploy(first).returncode == 0
    assert _run_deploy(second).returncode == 0

    for name in [
        "p105-deploy-public-telemetry.jsonl",
        "p105-deploy-private-injection-ledger.json",
        "p105-deploy-pre-label-partitions.json",
        "p105-deploy-rollback-evidence.json",
        "p105-deploy-coverage.json",
        "p105-deploy-harness-manifest.json",
        "p105-deploy-provenance-hashes.json",
    ]:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name

    rollback = first / "p105-deploy-rollback-evidence.json"
    payload = json.loads(rollback.read_text(encoding="utf-8"))
    payload["trigger_tick"] = 368
    rollback.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not VERIFY_SCRIPT.exists():
        pytest.fail("P105-027 RED: missing scripts/verify_p105_source_expansion_artifacts.py tamper verifier.", pytrace=False)
    tamper = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--deploy-manifest", str(first / "p105-deploy-harness-manifest.json"), "--expect-tamper-fixtures-fail-closed"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tamper.returncode != 0
    assert "deploy_rollback_tamper" in tamper.stderr
