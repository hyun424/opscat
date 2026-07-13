from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.run_p133_deadman_outbox as p133_runner
from app.services.p110_evaluation import stable_hash
from app.services.p133_release_evidence import (
    P133ReleaseEvidenceError,
    build_p133_release_evidence,
    validate_p133_release_evidence,
)


def _run_release(tmp_path: Path) -> dict[str, dict[str, Any]]:
    result = subprocess.run(
        [sys.executable, "scripts/run_p133_deadman_outbox.py", "--output-dir", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        name: json.loads((tmp_path / name).read_text(encoding="utf-8"))
        for name in (
            "outbox-report.json",
            "process-matrix.json",
            "supervisor-validation.json",
            "authority-ledger.json",
            "release-evidence.json",
        )
    }


def _validate(artifacts: dict[str, dict[str, Any]], artifact_root: Path) -> None:
    validate_p133_release_evidence(
        artifacts["release-evidence.json"],
        outbox_report=artifacts["outbox-report.json"],
        process_matrix=artifacts["process-matrix.json"],
        supervisor_validation=artifacts["supervisor-validation.json"],
        authority_ledger=artifacts["authority-ledger.json"],
        artifact_root=artifact_root,
    )


def test_release_runner_qualifies_transition_matrix_subprocesses_and_exact_zero_authority(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    release = artifacts["release-evidence.json"]
    outbox = artifacts["outbox-report.json"]
    process = artifacts["process-matrix.json"]
    supervisor = artifacts["supervisor-validation.json"]
    ledger = artifacts["authority-ledger.json"]
    _validate(artifacts, tmp_path)

    assert release["release_status"] == "p133_local_deadman_outbox_qualified"
    assert all(release["gates"].values())
    assert outbox["passed"] is True
    assert outbox["totals"]["expected_scenarios"] == 20
    assert outbox["totals"]["expected_emitted_events"] == outbox["totals"]["observed_emitted_events"]
    assert process["passed"] is True
    assert set(process["subprocess_cases"]) == {
        "deadman_check_stale_open",
        "deadman_run_dedup",
        "deadman_check_reminder",
        "deadman_check_recovery",
        "outbox_list_redacted",
        "outbox_ack_local",
        "restart_dedup",
        "graceful_stop",
    }
    assert process["evaluator_activity"]["process_launch_count"] > 0
    assert process["evaluator_activity"]["sigterm_count"] == 1
    assert all(type(value) is int and value >= 0 for value in process["resource_usage"].values())
    assert process["resource_usage"]["wall_milliseconds"] <= process["resource_limits"]["max_wall_milliseconds"]
    assert process["resource_usage"]["cpu_milliseconds"] <= process["resource_limits"]["max_cpu_milliseconds"]
    assert process["resource_usage"]["peak_memory_bytes"] <= process["resource_limits"]["max_peak_memory_bytes"]
    assert supervisor["passed"] is True
    launchd = supervisor["manifests"]["deploy/p133/io.opscat.deadman.plist"]
    assert launchd["passed"] is False
    assert launchd["status"] == "example_only_not_qualified"
    assert launchd["structural_checks_passed"] is True
    assert release["runtime_authority"]["exact_zero"] is True
    for key, value in ledger["evaluator_authority"]["counters"].items():
        assert type(value) is int and value == 0, key
    assert release["public_limitation"].startswith("Bounded local single-host outbox persistence only")


def test_validation_rejects_tamper_boolean_counters_and_stale_sources(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)

    tampered = copy.deepcopy(artifacts)
    tampered["release-evidence.json"]["gates"]["transition_matrix_passed"] = False
    with pytest.raises(P133ReleaseEvidenceError, match="release_evidence_hash_invalid"):
        _validate(tampered, tmp_path)

    boolean = copy.deepcopy(artifacts)
    first_key = next(iter(boolean["release-evidence.json"]["runtime_authority"]["counters"]))
    boolean["release-evidence.json"]["runtime_authority"]["counters"][first_key] = False
    boolean["release-evidence.json"]["release_evidence_hash"] = stable_hash(
        {key: value for key, value in boolean["release-evidence.json"].items() if key != "release_evidence_hash"}
    )
    with pytest.raises(P133ReleaseEvidenceError, match="authority_not_exact_zero"):
        _validate(boolean, tmp_path)

    stale = copy.deepcopy(artifacts)
    stale["process-matrix.json"]["source_hashes"]["app/services/p133_deadman_outbox.py"] = "sha256:" + "0" * 64
    stale["process-matrix.json"]["process_matrix_hash"] = stable_hash(
        {key: value for key, value in stale["process-matrix.json"].items() if key != "process_matrix_hash"}
    )
    stale["release-evidence.json"] = build_p133_release_evidence(
        stale["outbox-report.json"],
        stale["process-matrix.json"],
        stale["supervisor-validation.json"],
        stale["authority-ledger.json"],
    )
    with pytest.raises(P133ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        _validate(stale, tmp_path)


def test_builder_rejects_optimistic_flags_without_substantive_transition_evidence(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    outbox = copy.deepcopy(artifacts["outbox-report.json"])
    outbox["cases"]["event_cursor_crash_retry"] = {"passed": True, "evidence": {"event_id": "sha256:" + "1" * 64}}
    outbox["outbox_report_hash"] = stable_hash({key: value for key, value in outbox.items() if key != "outbox_report_hash"})
    release = build_p133_release_evidence(
        outbox,
        artifacts["process-matrix.json"],
        artifacts["supervisor-validation.json"],
        artifacts["authority-ledger.json"],
    )
    assert release["release_status"] == "p133_blocked"
    assert release["gates"]["transition_matrix_passed"] is False

    process = copy.deepcopy(artifacts["process-matrix.json"])
    process["subprocess_cases"] = {name: {"passed": True} for name in process["subprocess_cases"]}
    process["process_matrix_hash"] = stable_hash(
        {key: value for key, value in process.items() if key != "process_matrix_hash"}
    )
    fabricated = build_p133_release_evidence(
        artifacts["outbox-report.json"],
        process,
        artifacts["supervisor-validation.json"],
        artifacts["authority-ledger.json"],
    )
    assert fabricated["release_status"] == "p133_blocked"
    assert fabricated["gates"]["subprocess_smoke_passed"] is False

    resource = copy.deepcopy(artifacts["process-matrix.json"])
    resource["resource_usage"]["cpu_milliseconds"] = True
    resource["process_matrix_hash"] = stable_hash(
        {key: value for key, value in resource.items() if key != "process_matrix_hash"}
    )
    resource_release = build_p133_release_evidence(
        artifacts["outbox-report.json"],
        resource,
        artifacts["supervisor-validation.json"],
        artifacts["authority-ledger.json"],
    )
    assert resource_release["release_status"] == "p133_blocked"
    assert resource_release["gates"]["resource_usage_within_profile"] is False


def test_validation_rejects_missing_or_boolean_evaluator_activity(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    for mutation in ("missing", "boolean"):
        invalid = copy.deepcopy(artifacts)
        if mutation == "missing":
            invalid["authority-ledger.json"]["evaluator_activity"].pop("process_launch_count")
        else:
            invalid["authority-ledger.json"]["evaluator_activity"]["process_launch_count"] = True
        invalid["authority-ledger.json"]["authority_ledger_hash"] = stable_hash(
            {key: value for key, value in invalid["authority-ledger.json"].items() if key != "authority_ledger_hash"}
        )
        invalid["release-evidence.json"] = build_p133_release_evidence(
            invalid["outbox-report.json"],
            invalid["process-matrix.json"],
            invalid["supervisor-validation.json"],
            invalid["authority-ledger.json"],
        )
        with pytest.raises(P133ReleaseEvidenceError, match="release_gate_failed"):
            _validate(invalid, tmp_path)


def test_validation_rejects_raw_artifact_hash_drift(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    raw_file = next(iter(artifacts["outbox-report.json"]["raw_evidence"]["files"]))
    (tmp_path / raw_file).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(P133ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        _validate(artifacts, tmp_path)


def test_validation_rejects_promoted_report_drift_and_invalid_profile(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    supervisor_path = tmp_path / "supervisor-validation.json"
    supervisor_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(P133ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        _validate(artifacts, tmp_path)

    profile = json.loads(Path("evals/p133/input/outbox-profile.json").read_text(encoding="utf-8"))
    profile["max_wall_seconds"] = True
    profile_path = tmp_path / "invalid-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_p133_deadman_outbox.py",
            "--profile",
            str(profile_path),
            "--output-dir",
            str(tmp_path / "invalid-output"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "invalid_promoted_profile_value:max_wall_seconds" in result.stderr


def test_validation_rejects_omitted_required_source_and_manifest_bindings(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    omitted = copy.deepcopy(artifacts)
    for name in ("outbox-report.json", "process-matrix.json", "authority-ledger.json"):
        omitted[name]["source_hashes"].pop("app/monitor_cli.py")
        hash_field = {
            "outbox-report.json": "outbox_report_hash",
            "process-matrix.json": "process_matrix_hash",
            "authority-ledger.json": "authority_ledger_hash",
        }[name]
        omitted[name][hash_field] = stable_hash(
            {key: value for key, value in omitted[name].items() if key != hash_field}
        )
    omitted["release-evidence.json"] = build_p133_release_evidence(
        omitted["outbox-report.json"],
        omitted["process-matrix.json"],
        omitted["supervisor-validation.json"],
        omitted["authority-ledger.json"],
    )
    for name, value in omitted.items():
        (tmp_path / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(P133ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        _validate(omitted, tmp_path)

    artifacts = _run_release(tmp_path)
    artifacts["supervisor-validation.json"]["source_hashes"].pop("deploy/p133/io.opscat.deadman.plist")
    artifacts["supervisor-validation.json"]["supervisor_validation_hash"] = stable_hash(
        {
            key: value
            for key, value in artifacts["supervisor-validation.json"].items()
            if key != "supervisor_validation_hash"
        }
    )
    artifacts["release-evidence.json"] = build_p133_release_evidence(
        artifacts["outbox-report.json"],
        artifacts["process-matrix.json"],
        artifacts["supervisor-validation.json"],
        artifacts["authority-ledger.json"],
    )
    for name, value in artifacts.items():
        (tmp_path / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(P133ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        _validate(artifacts, tmp_path)


def test_supervisor_parsers_reject_adversarial_manifest_mutations(tmp_path: Path) -> None:
    systemd_text = Path("deploy/p133/opscat-deadman.service").read_text(encoding="utf-8")
    systemd_mutations = (
        systemd_text.replace("RestartSec=5", "RestartSec=0"),
        systemd_text.replace("RestrictAddressFamilies=AF_UNIX", "RestrictAddressFamilies=AF_INET"),
        systemd_text.replace("ReadOnlyPaths=/var/lib/opscat/monitor", "ReadOnlyPaths=/var/lib/opscat/other"),
        systemd_text + "\nEnvironment=API_TOKEN=value\n",
    )
    for index, text in enumerate(systemd_mutations):
        path = tmp_path / f"systemd-{index}.service"
        path.write_text(text, encoding="utf-8")
        assert p133_runner._validate_systemd_manifest(path)["passed"] is False

    compose = json.loads(Path("deploy/p133/compose.deadman.yaml").read_text(encoding="utf-8"))
    compose_mutations: list[dict[str, Any]] = []
    for field, value in (
        ("image", "opscat-monitor:latest"),
        ("network_mode", "host"),
        ("privileged", True),
        ("command", ["/bin/sh", "-c", "curl https://example.invalid"]),
    ):
        mutated = copy.deepcopy(compose)
        mutated["services"]["deadman"][field] = value
        compose_mutations.append(mutated)
    mutated = copy.deepcopy(compose)
    mutated["services"]["deadman"]["environment"] = {"API_TOKEN": "value"}
    compose_mutations.append(mutated)
    mutated = copy.deepcopy(compose)
    mutated["services"]["deadman"]["volumes"][1] = "./data/p131:/var/lib/opscat/monitor:rw"
    compose_mutations.append(mutated)
    for index, manifest_value in enumerate(compose_mutations):
        path = tmp_path / f"compose-{index}.json"
        path.write_text(json.dumps(manifest_value), encoding="utf-8")
        assert p133_runner._validate_compose_manifest(path)["passed"] is False


def test_promoted_p133_release_artifacts_are_current_if_present() -> None:
    root = Path("evals/p133")
    required = [
        root / "outbox-report.json",
        root / "process-matrix.json",
        root / "supervisor-validation.json",
        root / "authority-ledger.json",
        root / "release-evidence.json",
    ]
    if not all(path.exists() for path in required):
        pytest.skip("promoted P133 artifacts have not been generated in this checkout")
    artifacts = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in required}
    _validate(artifacts, root)
