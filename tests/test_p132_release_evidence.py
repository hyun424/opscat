from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p132_release_evidence import (
    P132ReleaseEvidenceError,
    build_p132_release_evidence,
    validate_p132_release_evidence,
)


def _run_release(tmp_path: Path) -> dict[str, dict[str, Any]]:
    result = subprocess.run(
        [sys.executable, "scripts/run_p132_supervised_runtime.py", "--output-dir", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        name: json.loads((tmp_path / name).read_text(encoding="utf-8"))
        for name in ("endurance-report.json", "process-matrix.json", "supervisor-validation.json", "release-evidence.json")
    }


def test_release_runner_qualifies_real_process_and_discloses_evaluator_activity(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    release = artifacts["release-evidence.json"]
    process = artifacts["process-matrix.json"]
    validate_p132_release_evidence(
        release,
        endurance_report=artifacts["endurance-report.json"],
        process_matrix=process,
        supervisor_validation=artifacts["supervisor-validation.json"],
        artifact_root=tmp_path,
    )

    assert release["release_status"] == "p132_supervised_runtime_qualified"
    assert all(release["gates"].values())
    assert process["cases"]["sigterm"]["passed"] is True
    assert process["cases"]["sigint"]["passed"] is True
    assert process["cases"]["forced_crash_restart"]["passed"] is True
    assert process["cases"]["lease_conflict"]["passed"] is True
    assert all(case["passed"] is True for case in process["storage_cases"].values())
    evaluator = release["evaluator_activity"]
    assert evaluator["process_launch_count"] > 0
    assert evaluator["signal_count"] > 0
    assert evaluator["forced_kill_count"] > 0
    for key in (
        "arbitrary_command_count",
        "credential_read_count",
        "network_call_count",
        "connector_write_count",
        "remediation_count",
        "staging_mutation_count",
        "production_mutation_count",
    ):
        assert type(evaluator[key]) is int and evaluator[key] == 0
    assert release["runtime_authority"]["exact_zero"] is True
    assert release["public_limitation"].startswith("Bounded local single-host qualification only")


def test_release_validation_rejects_tamper_boolean_counters_and_source_drift(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    release = artifacts["release-evidence.json"]
    endurance = artifacts["endurance-report.json"]
    process = artifacts["process-matrix.json"]
    supervisor = artifacts["supervisor-validation.json"]

    tampered = copy.deepcopy(release)
    tampered["gates"]["process_matrix_passed"] = False
    with pytest.raises(P132ReleaseEvidenceError, match="release_evidence_hash_invalid"):
        validate_p132_release_evidence(
            tampered,
            endurance_report=endurance,
            process_matrix=process,
            supervisor_validation=supervisor,
            artifact_root=tmp_path,
        )

    boolean = copy.deepcopy(release)
    first_key = next(iter(boolean["runtime_authority"]["counters"]))
    boolean["runtime_authority"]["counters"][first_key] = False
    boolean["release_evidence_hash"] = stable_hash({key: value for key, value in boolean.items() if key != "release_evidence_hash"})
    with pytest.raises(P132ReleaseEvidenceError, match="authority_not_exact_zero"):
        validate_p132_release_evidence(
            boolean,
            endurance_report=endurance,
            process_matrix=process,
            supervisor_validation=supervisor,
            artifact_root=tmp_path,
        )

    drift = copy.deepcopy(supervisor)
    drift["source_hashes"]["deploy/p132/opscat-monitor.service"] = "sha256:drift"
    drift["supervisor_validation_hash"] = stable_hash({key: value for key, value in drift.items() if key != "supervisor_validation_hash"})
    with pytest.raises(P132ReleaseEvidenceError, match="release_evidence_semantic_mismatch"):
        validate_p132_release_evidence(
            release,
            endurance_report=endurance,
            process_matrix=process,
            supervisor_validation=drift,
            artifact_root=tmp_path,
        )


def test_release_validation_rejects_missing_or_boolean_evaluator_counters(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    release = artifacts["release-evidence.json"]

    for mutation in ("missing", "boolean"):
        invalid = copy.deepcopy(release)
        if mutation == "missing":
            invalid["evaluator_activity"].pop("watchdog_call_count")
        else:
            invalid["evaluator_activity"]["watchdog_call_count"] = False
        invalid["release_evidence_hash"] = stable_hash(
            {key: value for key, value in invalid.items() if key != "release_evidence_hash"}
        )
        with pytest.raises(P132ReleaseEvidenceError, match="evaluator_activity_invalid"):
            validate_p132_release_evidence(
                invalid,
                endurance_report=artifacts["endurance-report.json"],
                process_matrix=artifacts["process-matrix.json"],
                supervisor_validation=artifacts["supervisor-validation.json"],
                artifact_root=tmp_path,
            )


def test_release_builder_requires_process_self_hash(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    process = copy.deepcopy(artifacts["process-matrix.json"])
    process.pop("process_matrix_hash")
    release = build_p132_release_evidence(
        artifacts["endurance-report.json"],
        process,
        artifacts["supervisor-validation.json"],
        evaluator_activity=process["evaluator_activity"],
    )
    assert release["release_status"] == "p132_blocked"
    assert release["gates"]["process_matrix_self_hash_current"] is False


def test_release_builder_requires_substantive_storage_fault_evidence(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    process = copy.deepcopy(artifacts["process-matrix.json"])
    process["storage_cases"]["post_replace_recovery"] = {"passed": True}
    process["process_matrix_hash"] = stable_hash(
        {key: value for key, value in process.items() if key != "process_matrix_hash"}
    )
    release = build_p132_release_evidence(
        artifacts["endurance-report.json"],
        process,
        artifacts["supervisor-validation.json"],
        evaluator_activity=process["evaluator_activity"],
    )
    assert release["release_status"] == "p132_blocked"
    assert release["gates"]["storage_matrix_passed"] is False


def test_release_builder_rejects_nonzero_invalid_or_inconsistent_accounting(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    endurance = copy.deepcopy(artifacts["endurance-report.json"])
    endurance["accounting"]["invalid"] = 7
    endurance["endurance_report_hash"] = stable_hash(
        {key: value for key, value in endurance.items() if key != "endurance_report_hash"}
    )
    release = build_p132_release_evidence(
        endurance,
        artifacts["process-matrix.json"],
        artifacts["supervisor-validation.json"],
        evaluator_activity=artifacts["process-matrix.json"]["evaluator_activity"],
    )
    assert release["release_status"] == "p132_blocked"
    assert release["gates"]["endurance_accounting_exact"] is False


def test_release_validation_recomputes_current_source_hashes(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path)
    process = copy.deepcopy(artifacts["process-matrix.json"])
    source_name = next(iter(process["source_hashes"]))
    process["source_hashes"][source_name] = "sha256:" + "0" * 64
    process["process_matrix_hash"] = stable_hash(
        {key: value for key, value in process.items() if key != "process_matrix_hash"}
    )
    release = build_p132_release_evidence(
        artifacts["endurance-report.json"],
        process,
        artifacts["supervisor-validation.json"],
        evaluator_activity=process["evaluator_activity"],
    )
    assert release["release_status"] == "p132_supervised_runtime_qualified"
    with pytest.raises(P132ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        validate_p132_release_evidence(
            release,
            endurance_report=artifacts["endurance-report.json"],
            process_matrix=process,
            supervisor_validation=artifacts["supervisor-validation.json"],
            artifact_root=tmp_path,
        )


def test_release_validation_binds_only_the_monitor_console_mapping(tmp_path: Path) -> None:
    artifacts = _run_release(tmp_path / "artifacts")
    project = tmp_path / "project"
    project.mkdir()
    source_paths = {
        *artifacts["process-matrix.json"]["source_hashes"],
        *artifacts["supervisor-validation.json"]["source_hashes"],
        "app/services/p131_always_on_monitor.py",
        "app/services/p132_supervised_runtime.py",
        "pyproject.toml",
    }
    for relative in source_paths:
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(relative, target)

    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + '\nunrelated-future-command = "app.future_cli:main"\n',
        encoding="utf-8",
    )
    validate_p132_release_evidence(
        artifacts["release-evidence.json"],
        endurance_report=artifacts["endurance-report.json"],
        process_matrix=artifacts["process-matrix.json"],
        supervisor_validation=artifacts["supervisor-validation.json"],
        project_root=project,
        artifact_root=tmp_path / "artifacts",
    )

    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            'opscat-monitor = "app.monitor_cli:main"',
            'opscat-monitor = "app.wrong_cli:main"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(P132ReleaseEvidenceError, match="release_evidence_artifact_stale"):
        validate_p132_release_evidence(
            artifacts["release-evidence.json"],
            endurance_report=artifacts["endurance-report.json"],
            process_matrix=artifacts["process-matrix.json"],
            supervisor_validation=artifacts["supervisor-validation.json"],
            project_root=project,
            artifact_root=tmp_path / "artifacts",
        )


def test_promoted_p132_release_artifacts_are_current() -> None:
    root = Path("evals/p132")
    endurance = json.loads((root / "endurance-report.json").read_text(encoding="utf-8"))
    process = json.loads((root / "process-matrix.json").read_text(encoding="utf-8"))
    supervisor = json.loads((root / "supervisor-validation.json").read_text(encoding="utf-8"))
    release = json.loads((root / "release-evidence.json").read_text(encoding="utf-8"))
    validate_p132_release_evidence(
        release,
        endurance_report=endurance,
        process_matrix=process,
        supervisor_validation=supervisor,
        artifact_root=root,
    )
    artifacts = endurance["artifacts"]
    assert all(not Path(artifacts[key]).is_absolute() for key in ("workspace", "source_path", "state_path", "report_dir"))
    assert (root / artifacts["source_path"]).is_file()
    assert (root / artifacts["state_path"]).is_file()
