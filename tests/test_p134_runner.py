from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p134_observation_authority import validate_receipt_ledger
from scripts import run_p134_observation_authority as runner


def _profile() -> dict[str, object]:
    value = json.loads(
        (runner.ROOT / "evals/p134/input/authority-profile.json").read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def test_runner_executes_exact_24_real_contract_and_fault_cases() -> None:
    profile = runner._validate_profile(_profile())
    contract = runner._contract_from_profile(profile)

    contract_matrix, ledger = runner._run_contract_matrix(contract=contract, profile=profile)
    fault_matrix = runner._run_fault_matrix(contract, profile)

    assert contract_matrix["totals"] == {
        "expected_cases": 18,
        "passed_cases": 18,
        "failed_cases": 0,
        "allowed_cases": 1,
        "denied_cases": 16,
        "duplicate_cases": 1,
        "denominator_scope": "principal_contract_assertions",
    }
    assert fault_matrix["totals"] == {
        "expected_cases": 6,
        "passed_cases": 6,
        "failed_cases": 0,
        "rejected_cases": 6,
        "denominator_scope": "principal_fault_assertions",
    }
    validate_receipt_ledger(ledger, contract=contract)


def test_runner_profile_rejects_unknown_fields_and_case_drift() -> None:
    unknown = deepcopy(_profile())
    unknown["optimistic_extension"] = True
    with pytest.raises(ValueError, match="unexpected_profile_field:optimistic_extension"):
        runner._validate_profile(unknown)

    drifted = deepcopy(_profile())
    required = drifted["required_contract_cases"]
    assert isinstance(required, list)
    required.pop()
    with pytest.raises(ValueError, match="required_contract_cases_mismatch"):
        runner._validate_profile(drifted)


def test_runner_writes_only_exact_atomic_artifact_set(tmp_path: Path) -> None:
    payloads = {
        "contract-matrix.json": {"artifact": "contract"},
        "fault-matrix.json": {"artifact": "fault"},
        "receipt-ledger.json": {"artifact": "receipt"},
        "authority-ledger.json": {"artifact": "authority"},
        "release-evidence.json": {"artifact": "release"},
    }

    runner._write_exact_artifacts(tmp_path, payloads)

    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(payloads)
    assert not list(tmp_path.glob(".*.tmp"))
    for name, payload in payloads.items():
        assert json.loads((tmp_path / name).read_text(encoding="utf-8")) == payload

    with pytest.raises(ValueError, match="artifact_set_invalid"):
        runner._write_exact_artifacts(tmp_path, {"release-evidence.json": {}})


def test_runner_fails_closed_without_independent_review_and_writes_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "out"

    status = runner.main(
        [
            "--profile",
            str(runner.ROOT / "evals/p134/input/authority-profile.json"),
            "--independent-review",
            str(tmp_path / "missing-review.json"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert status == 1
    assert not output_dir.exists()
    error = json.loads(capsys.readouterr().err)
    assert error["release_status"] == "p134_blocked"
    assert error["error_type"] == "FileNotFoundError"
