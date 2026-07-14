from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p139_local_triage_service import (
    EXPECTED_P138_EVIDENCE_HASH,
    P139ServiceError,
    build_local_triage_service_bundle,
    inspect_local_triage_service,
    read_local_triage_service_bundle,
    run_local_triage_service_for_evaluation,
    write_local_triage_service_bundle,
)
from tests.fixtures.p139.builders import P139Fixture, build_p139_fixture

NOW = ("2026-07-13T00:10:04Z", "2026-07-13T00:10:05Z")


def _run(fixture: P139Fixture) -> dict[str, Any]:
    return run_local_triage_service_for_evaluation(
        base_path=fixture.root,
        bundle=fixture.bundle,
        now_values=NOW,
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )


def test_service_lease_conflict_fails_before_inner_state(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    lease_path = fixture.root / fixture.bundle["service_lease_path"]
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    with lease_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = sorted(path.relative_to(fixture.root).as_posix() for path in fixture.root.rglob("*"))
        with pytest.raises(P139ServiceError, match="service_lease_unavailable"):
            _run(fixture)
        after = sorted(path.relative_to(fixture.root).as_posix() for path in fixture.root.rglob("*"))
    assert after == before


def test_exit_history_retention_preserves_current_and_predecessor(tmp_path: Path) -> None:
    fixture = build_p139_fixture(
        tmp_path,
        limits={
            "max_bundle_bytes": 8_388_608,
            "max_state_bytes": 4_194_304,
            "max_exit_history_records": 2,
            "startup_readiness_stale_after_ms": 30_000,
            "wall_limit_ms": 60_000,
            "cpu_limit_ms": 30_000,
            "peak_memory_limit_bytes": 268_435_456,
        },
    )
    result: dict[str, Any] = {}
    for _ in range(5):
        result = _run(fixture)
    history = fixture.root / fixture.bundle["exit_history_dir"]
    names = {path.stem for path in history.glob("*.json")}
    receipt = result["exit_receipt"]
    assert len(names) == 2
    assert str(receipt["receipt_hash"]).removeprefix("sha256:") in names
    assert str(receipt["previous_receipt_hash"]).removeprefix("sha256:") in names


def test_bundle_framing_and_release_drift_fail_closed(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    bundle_path = tmp_path / "bundle.json"
    write_local_triage_service_bundle(bundle_path, fixture.bundle)
    canonical = bundle_path.read_bytes()
    for name, payload in (
        ("missing-newline", canonical.rstrip(b"\n")),
        ("double-newline", canonical + b"\n"),
        ("invalid-utf8", b"\xff\n"),
    ):
        path = tmp_path / name
        path.write_bytes(payload)
        with pytest.raises(P139ServiceError):
            read_local_triage_service_bundle(path)

    drift = deepcopy(fixture.bundle_input)
    drift["p138_release_evidence_hash"] = "sha256:" + "0" * 64
    assert drift["p138_release_evidence_hash"] != EXPECTED_P138_EVIDENCE_HASH
    with pytest.raises(P139ServiceError, match="p138_release_evidence_drift"):
        build_local_triage_service_bundle(drift)

    tiny = deepcopy(fixture.bundle_input)
    tiny["limits"]["max_bundle_bytes"] = 100
    tiny_bundle = build_local_triage_service_bundle(tiny)
    with pytest.raises(P139ServiceError, match="bundle_byte_budget_exceeded"):
        write_local_triage_service_bundle(tmp_path / "oversized.json", tiny_bundle)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("service_lease_path", "/absolute.lock"),
        ("service_lease_path", "../traversal.lock"),
        ("exit_receipt_path", "p138/ledger.json"),
    ],
)
def test_path_authority_is_explicit_relative_and_nonoverlapping(tmp_path: Path, field: str, value: str) -> None:
    fixture = build_p139_fixture(tmp_path)
    invalid = deepcopy(fixture.bundle_input)
    invalid[field] = value
    with pytest.raises(P139ServiceError):
        build_local_triage_service_bundle(invalid)


def test_tampered_exit_receipt_and_termination_block_status(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    result = _run(fixture)
    receipt_path = fixture.root / fixture.bundle["exit_receipt_path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["stop_reason"] = "tampered"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(P139ServiceError, match="exit_receipt_hash_invalid"):
        inspect_local_triage_service(base_path=fixture.root, bundle=fixture.bundle, now=NOW[-1])

    receipt_path.write_text(
        json.dumps(result["exit_receipt"], sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    termination_path = fixture.root / fixture.bundle["p138_config"]["termination_dir"] / f"{str(result['exit_receipt']['p138_termination_hash']).removeprefix('sha256:')}.json"
    termination = json.loads(termination_path.read_text(encoding="utf-8"))
    termination["stop_reason"] = "tampered"
    termination_path.write_text(json.dumps(termination, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(P139ServiceError, match="invalid_p138_termination_hash"):
        inspect_local_triage_service(base_path=fixture.root, bundle=fixture.bundle, now=NOW[-1])


def test_cli_errors_are_machine_readable_and_fail_closed(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.p139_service_cli",
            "validate",
            "--bundle",
            str(tmp_path / "missing.json"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["status"] == "failed_closed"


def test_deployment_manifests_enforce_no_network_and_least_privilege() -> None:
    root = Path(__file__).resolve().parents[1]
    systemd = (root / "deploy/p139/opscat-triage-service.service").read_text(encoding="utf-8")
    for requirement in (
        "PrivateNetwork=true",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_UNIX",
        "KillSignal=SIGTERM",
    ):
        assert requirement in systemd
    compose = json.loads((root / "deploy/p139/compose.triage-service.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["opscat-triage-service"]
    assert service["network_mode"] == "none"
    assert service["read_only"] is True
    assert service["privileged"] is False
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert "@sha256:" in service["image"]
    assert "environment" not in service
