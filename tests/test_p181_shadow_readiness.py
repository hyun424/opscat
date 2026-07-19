from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.p147_p152_contracts import canonical_json_bytes, stable_hash
from app.services.p181_shadow_readiness import (
    P181ReadinessError,
    build_p181_readiness_artifact,
    validate_p181_readiness_artifact,
    validate_read_only_shadow_gate,
    validate_redaction_proof,
    validate_shadow_ledger,
)

ROOT = Path(__file__).resolve().parents[1]


def _signed_release_evidence(*, schema_version: str, claim: str, receipt_key: str = "independent_scorer_receipt") -> dict[str, object]:
    phase = schema_version[:4]
    evidence: dict[str, object] = {
        "schema_version": schema_version,
        "qualified": True,
        "claim": claim,
        "artifact_path": f"evals/{phase}/output/release-evidence.json",
        "artifact_file_hash": stable_hash({"artifact": schema_version}),
        "report_hash": stable_hash({"report": schema_version}),
        "freeze_hash": stable_hash({"freeze": schema_version}),
        "final_review_hash": stable_hash({"review": schema_version}),
    }
    evidence["evidence_hash"] = hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()
    evidence[receipt_key] = {
        "schema_version": "independent.receipt.v1",
        "signer_id": "independent-scorer",
        "payload_hash": evidence["evidence_hash"],
        "signature_hash": stable_hash({"payload_hash": evidence["evidence_hash"], "signer_id": "independent-scorer"}),
    }
    return evidence


def _receipt(*, schema_version: str, payload: Mapping[str, object], signer_id: str, previous_receipt_hash: str | None = None) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": schema_version,
        "signer_id": signer_id,
        "payload_hash": stable_hash(payload),
        "previous_receipt_hash": previous_receipt_hash,
    }
    receipt["signature_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "signature_hash"})
    receipt["receipt_hash"] = stable_hash(receipt)
    return receipt


def _shadow_days() -> list[dict[str, object]]:
    first = date(2026, 2, 1)
    days = []
    previous_receipt_hash = None
    for index in range(28):
        payload = {"utc_date": (first + timedelta(days=index)).isoformat(), "heartbeat": "observed", "deadman": "observed"}
        receipt = _receipt(
            schema_version="p181.shadow_day_custody_receipt.v1",
            payload=payload,
            signer_id="shadow-custodian",
            previous_receipt_hash=previous_receipt_hash,
        )
        previous_receipt_hash = str(receipt["receipt_hash"])
        days.append(
            {
            "utc_date": (first + timedelta(days=index)).isoformat(),
            "covered_operator_hours": 12,
            "shift_ids": [f"shift-{index:02d}-a", f"shift-{index:02d}-b"] if index < 20 else [f"shift-{index:02d}-a"],
            "operator_ids": [f"operator-{index % 8}"],
            "custody_payload": payload,
            "custody_receipt": receipt,
            "mutation_count": 0,
        }
        )
    return days


def test_shadow_ledger_requires_consecutive_real_days_hours_shifts_operators_and_deadman() -> None:
    ledger = validate_shadow_ledger(_shadow_days())
    assert ledger["shadow_calendar_days"] == 28
    assert ledger["covered_operator_hours"] == 336
    assert ledger["covered_operator_shift_count"] == 48
    assert ledger["distinct_operator_count"] == 8
    assert ledger["heartbeat_deadman_coverage"] == 1.0

    gapped = _shadow_days()
    gapped[5]["utc_date"] = date(2026, 3, 1).isoformat()
    with pytest.raises(P181ReadinessError, match="shadow_days_not_consecutive"):
        validate_shadow_ledger(gapped)

    self_asserted = _shadow_days()
    self_asserted[0]["heartbeat_receipt_valid"] = True
    with pytest.raises(P181ReadinessError, match="self_asserted_shadow_receipt"):
        validate_shadow_ledger(self_asserted)


def test_read_only_shadow_gate_rejects_any_mutation_or_write_capable_runtime() -> None:
    payload = {"runtime_principal_allowlist_binding_coverage": 1.0, "provider_allowlist_receipt_coverage": 1.0}
    gate = validate_read_only_shadow_gate(
        {
            "action_execution_count": 0,
            "auto_approval_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
            "runtime_principal_write_permission_count": 0,
            "configured_provider_count": 1,
            "runtime_principal_allowlist_binding_coverage": 1.0,
            "runtime_token_ttl_seconds": 3600,
            "out_of_allowlist_observation_count": 0,
            "provider_allowlist_receipt_coverage": 1.0,
            "custody_payload": payload,
            "custody_receipt": _receipt(schema_version="p181.read_only_runtime_custody_receipt.v1", payload=payload, signer_id="runtime-custodian"),
        }
    )
    assert gate["read_only"] is True

    unsafe = deepcopy(gate)
    unsafe["production_mutation_count"] = 1
    with pytest.raises(P181ReadinessError, match="mutation_counter_nonzero"):
        validate_read_only_shadow_gate(unsafe)

    self_asserted = deepcopy(gate)
    self_asserted["read_only_attested"] = True
    with pytest.raises(P181ReadinessError, match="self_asserted_read_only_gate"):
        validate_read_only_shadow_gate(self_asserted)


def test_redaction_proof_requires_canaries_field_classes_and_all_artifact_paths() -> None:
    proof = validate_redaction_proof(
        {
            "redaction_canary_removal_rate": 1.0,
            "persisted_raw_credential_or_sensitive_value_match_count": 0,
            "unique_redaction_canary_count": 20,
            "sensitive_field_class_count": 5,
            "artifact_path_classes": ["prompt", "log", "trace", "exception", "report", "release"],
            "credential_leak_count": 0,
        }
    )
    assert proof["redacted"] is True

    missing_path = deepcopy(proof)
    missing_path["artifact_path_classes"] = ["prompt", "log", "trace", "exception", "report"]
    with pytest.raises(P181ReadinessError, match="redaction_artifact_path_class_count"):
        validate_redaction_proof(missing_path)


def test_p181_readiness_is_blocked_until_p180_release_evidence_is_qualified() -> None:
    artifact = build_p181_readiness_artifact(project_root=ROOT, p180_release_evidence=None)
    assert artifact["qualified"] is False
    assert artifact["maximum_claim"] == "readiness_offline_substrate_only"
    assert "real_shadow_operator_ready" in artifact["forbidden_claims"]
    assert "missing_qualified_p180_release_evidence" in artifact["stop_reasons"]
    assert validate_p181_readiness_artifact(artifact, project_root=ROOT)["qualified"] is False

    forged = deepcopy(artifact)
    forged["qualified"] = True
    forged["maximum_claim"] = "real_shadow_operator_ready"
    forged["readiness_hash"] = stable_hash({key: value for key, value in forged.items() if key != "readiness_hash"})
    with pytest.raises(P181ReadinessError, match="qualification_forbidden"):
        validate_p181_readiness_artifact(forged, project_root=ROOT)

    fabricated_predecessor = {
        "schema_version": "p180.release_evidence.v1",
        "qualified": True,
        "claim": "statistically_qualified_hidden_eval_soak",
        "evidence_hash": "sha256:" + "1" * 64,
    }
    still_blocked = build_p181_readiness_artifact(project_root=ROOT, p180_release_evidence=fabricated_predecessor)
    assert still_blocked["p180_release_evidence"]["valid"] is False

    nonexistent_predecessor = _signed_release_evidence(schema_version="p180.release_evidence.v1", claim="statistically_qualified_hidden_eval_soak")
    still_blocked = build_p181_readiness_artifact(project_root=ROOT, p180_release_evidence=nonexistent_predecessor)
    assert still_blocked["p180_release_evidence"]["valid"] is False
    assert "missing_qualified_p180_release_evidence" in still_blocked["stop_reasons"]
