from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p131_release_evidence import (
    P131_READY_STATUS,
    P131ReleaseEvidenceError,
    build_p131_release_evidence,
    validate_p131_release_evidence,
)


def test_release_runner_is_deterministic_and_qualified(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "scripts/run_p131_always_on_monitor.py",
        "--scenario",
        "evals/p131/input/scenario.json",
        "--output-dir",
        str(tmp_path),
    ]
    first = subprocess.run(command, check=False, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    first_outputs = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stdout + second.stderr
    second_outputs = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    assert first_outputs == second_outputs

    release = json.loads((tmp_path / "release-evidence.json").read_text(encoding="utf-8"))
    runtime = json.loads((tmp_path / "runtime-report.json").read_text(encoding="utf-8"))
    watchdog = json.loads((tmp_path / "watchdog-matrix.json").read_text(encoding="utf-8"))
    validate_p131_release_evidence(release, runtime_report=runtime, watchdog_matrix=watchdog)
    assert release["release_status"] == P131_READY_STATUS
    assert all(release["gates"].values())
    assert set(runtime["static_boundary"]["source_hashes"]) == {
        "app/api/health.py",
        "app/config.py",
        "app/monitor_cli.py",
        "app/services/p131_always_on_monitor.py",
        "app/services/p131_release_evidence.py",
        "scripts/run_p131_always_on_monitor.py",
    }


def test_release_evidence_rejects_tamper(tmp_path: Path) -> None:
    command = [sys.executable, "scripts/run_p131_always_on_monitor.py", "--output-dir", str(tmp_path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    release = json.loads((tmp_path / "release-evidence.json").read_text(encoding="utf-8"))
    tampered = copy.deepcopy(release)
    tampered["gates"]["heartbeat_current"] = False

    with pytest.raises(P131ReleaseEvidenceError, match="release_evidence_hash_invalid"):
        validate_p131_release_evidence(tampered, runtime_report={}, watchdog_matrix={})

    tampered["release_evidence_hash"] = stable_hash({key: value for key, value in tampered.items() if key != "release_evidence_hash"})
    with pytest.raises(P131ReleaseEvidenceError, match="release_gate_failed"):
        validate_p131_release_evidence(tampered, runtime_report={}, watchdog_matrix={})


def test_release_validator_rejects_missing_bindings_and_false_exact_zero(tmp_path: Path) -> None:
    subprocess.run([sys.executable, "scripts/run_p131_always_on_monitor.py", "--output-dir", str(tmp_path)], check=True, capture_output=True, text=True)
    release = json.loads((tmp_path / "release-evidence.json").read_text(encoding="utf-8"))
    runtime = json.loads((tmp_path / "runtime-report.json").read_text(encoding="utf-8"))
    watchdog = json.loads((tmp_path / "watchdog-matrix.json").read_text(encoding="utf-8"))

    missing = copy.deepcopy(release)
    missing.pop("runtime_report_hash")
    missing["release_evidence_hash"] = stable_hash({key: value for key, value in missing.items() if key != "release_evidence_hash"})
    with pytest.raises(P131ReleaseEvidenceError, match="runtime_report_binding_invalid"):
        validate_p131_release_evidence(missing, runtime_report=runtime, watchdog_matrix=watchdog)

    false_zero = copy.deepcopy(release)
    false_zero["authority"]["exact_zero"] = False
    false_zero["release_evidence_hash"] = stable_hash({key: value for key, value in false_zero.items() if key != "release_evidence_hash"})
    with pytest.raises(P131ReleaseEvidenceError, match="authority_not_exact_zero"):
        validate_p131_release_evidence(false_zero, runtime_report=runtime, watchdog_matrix=watchdog)


def test_release_validator_recomputes_gates_from_bound_artifacts(tmp_path: Path) -> None:
    subprocess.run([sys.executable, "scripts/run_p131_always_on_monitor.py", "--output-dir", str(tmp_path)], check=True, capture_output=True, text=True)
    release = json.loads((tmp_path / "release-evidence.json").read_text(encoding="utf-8"))
    runtime = json.loads((tmp_path / "runtime-report.json").read_text(encoding="utf-8"))
    watchdog = json.loads((tmp_path / "watchdog-matrix.json").read_text(encoding="utf-8"))

    missing_gate = copy.deepcopy(release)
    missing_gate["gates"].pop("heartbeat_current")
    missing_gate["release_evidence_hash"] = stable_hash({key: value for key, value in missing_gate.items() if key != "release_evidence_hash"})
    with pytest.raises(P131ReleaseEvidenceError, match="release_evidence_semantic_mismatch"):
        validate_p131_release_evidence(missing_gate, runtime_report=runtime, watchdog_matrix=watchdog)

    contradictory_runtime = copy.deepcopy(runtime)
    contradictory_runtime["final_state"]["ready"] = False
    contradictory_runtime["runtime_report_hash"] = stable_hash(
        {key: value for key, value in contradictory_runtime.items() if key != "runtime_report_hash"}
    )
    contradictory_release = copy.deepcopy(release)
    contradictory_release["runtime_report_hash"] = stable_hash(contradictory_runtime)
    contradictory_release["release_evidence_hash"] = stable_hash(
        {key: value for key, value in contradictory_release.items() if key != "release_evidence_hash"}
    )
    with pytest.raises(P131ReleaseEvidenceError, match="release_evidence_semantic_mismatch"):
        validate_p131_release_evidence(contradictory_release, runtime_report=contradictory_runtime, watchdog_matrix=watchdog)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("final_state", "resume_count", True),
        ("first_run", "accepted_observation_count", True),
        ("restart_run", "accepted_observation_count", True),
        ("final_state", "duplicate_observation_count", False),
        ("canary", "failure_count", False),
        ("canary", "action_execution_count", False),
        ("totals", "action_execution_count", False),
        ("totals", "network_call_count", False),
    ],
)
def test_release_builder_rejects_boolean_numeric_counter_substitution(
    tmp_path: Path,
    section: str,
    field: str,
    value: bool,
) -> None:
    subprocess.run([sys.executable, "scripts/run_p131_always_on_monitor.py", "--output-dir", str(tmp_path)], check=True, capture_output=True, text=True)
    runtime = json.loads((tmp_path / "runtime-report.json").read_text(encoding="utf-8"))
    watchdog = json.loads((tmp_path / "watchdog-matrix.json").read_text(encoding="utf-8"))
    target = runtime[section] if section in {"first_run", "restart_run"} else runtime["final_state"][section] if section in {"canary", "totals"} else runtime[section]
    target[field] = value
    runtime["runtime_report_hash"] = stable_hash({key: item for key, item in runtime.items() if key != "runtime_report_hash"})

    rebuilt = build_p131_release_evidence(runtime, watchdog)

    assert rebuilt["release_status"] == "p131_blocked"
    assert not all(rebuilt["gates"].values())
    with pytest.raises(P131ReleaseEvidenceError, match="release_gate_failed"):
        validate_p131_release_evidence(rebuilt, runtime_report=runtime, watchdog_matrix=watchdog)
