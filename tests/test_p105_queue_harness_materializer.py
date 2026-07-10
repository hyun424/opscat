from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

QUEUE_SCRIPT = Path("scripts/run_p105_queue_harness.py")
VERIFY_SCRIPT = Path("scripts/verify_p105_source_expansion_artifacts.py")


def _require_queue_script() -> None:
    if not QUEUE_SCRIPT.exists():
        pytest.fail("P105-026 RED: missing scripts/run_p105_queue_harness.py isolated RabbitMQ harness.", pytrace=False)


def _run_queue(output_dir: Path, *, seed: int = 105026) -> subprocess.CompletedProcess[str]:
    _require_queue_script()
    return subprocess.run(
        [
            sys.executable,
            str(QUEUE_SCRIPT),
            "--compose-file",
            "tools/p105/queue/docker-compose.yml",
            "--rabbitmq-image",
            "rabbitmq:3.13-management-alpine",
            "--seed",
            str(seed),
            "--ticks",
            "3",
            "--tick-seconds",
            "0",
            "--output-dir",
            str(output_dir),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:06:40Z",
            "--expect-no-host-ports",
            "--test-fast-runtime",
            "--expect-no-production-authority",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_queue_harness_outputs_public_telemetry_private_ledger_partitions_coverage_and_manifest(tmp_path: Path) -> None:
    output = tmp_path / "queue"
    completed = _run_queue(output)

    assert completed.returncode == 0, completed.stderr
    expected = {
        "p105-queue-public-telemetry.jsonl",
        "p105-queue-private-injection-ledger.json",
        "p105-queue-pre-label-partitions.json",
        "p105-queue-coverage.json",
        "p105-queue-harness-manifest.json",
        "p105-queue-provenance-hashes.json",
    }
    assert expected <= {path.name for path in output.iterdir()}
    first_row = json.loads((output / "p105-queue-public-telemetry.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert {"messages_ready", "messages_unacknowledged", "messages_total", "dlq_messages_ready", "ack_lag_p95_ticks"} <= set(first_row)
    assert "injection_id" not in first_row
    ledger = json.loads((output / "p105-queue-private-injection-ledger.json").read_text(encoding="utf-8"))
    assert ledger["label_join_phase"] == "after_sampling_and_partition"
    coverage = json.loads((output / "p105-queue-coverage.json").read_text(encoding="utf-8"))
    assert coverage["clock_source"] == "time.monotonic_ns"
    assert coverage["maximum_perfect_run_seconds_per_queue"] == 2
    assert coverage["rejects"] == ["fixed_four_day_constant", "accelerated_logical_clock", "floor_sized_interval"]


def test_queue_harness_uses_fixed_program_no_credentials_production_endpoint_or_host_ports(tmp_path: Path) -> None:
    output = tmp_path / "queue"
    completed = _run_queue(output)

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((output / "p105-queue-harness-manifest.json").read_text(encoding="utf-8"))
    assert manifest["program_version"] == "p105.queue.rabbitmq.v1"
    assert manifest["rabbitmq_image"] == "rabbitmq:3.13-management-alpine"
    assert manifest["seed"] == 105026
    assert manifest["schedule"] == {
        "heldout_pause_ticks": [120, 179],
        "shadow_pause_ticks": [240, 299],
        "heldout_poison_tick": 420,
        "shadow_poison_tick": 600,
        "producer_rate": 20,
        "normal_consumer_rate": 20,
        "recovery_consumer_rate": 40,
    }
    assert manifest["authority"] == {
        "auth_enabled": False,
        "credentials_read": False,
        "external_broker_endpoint": False,
        "host_ports": [],
        "production_endpoint": False,
        "production_mutation": False,
        "release_counting_authority": False,
    }


def test_queue_harness_reruns_are_byte_identical_and_tamper_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert _run_queue(first).returncode == 0
    assert _run_queue(second).returncode == 0

    for name in [
        "p105-queue-public-telemetry.jsonl",
        "p105-queue-private-injection-ledger.json",
        "p105-queue-pre-label-partitions.json",
        "p105-queue-coverage.json",
        "p105-queue-harness-manifest.json",
        "p105-queue-provenance-hashes.json",
    ]:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name

    telemetry = first / "p105-queue-public-telemetry.jsonl"
    telemetry.write_text(telemetry.read_text(encoding="utf-8").replace("messages_ready", "messages_READY", 1), encoding="utf-8")
    if not VERIFY_SCRIPT.exists():
        pytest.fail("P105-026 RED: missing scripts/verify_p105_source_expansion_artifacts.py tamper verifier.", pytrace=False)
    tamper = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--queue-manifest", str(first / "p105-queue-harness-manifest.json"), "--expect-tamper-fixtures-fail-closed"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert tamper.returncode != 0
    assert "queue_telemetry_tamper" in tamper.stderr
