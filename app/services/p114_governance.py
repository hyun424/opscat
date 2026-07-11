"""P114 consumed-development lineage and claim governance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash

LINEAGE_SCHEMA_VERSION = "p114.lineage_ledger.v1"
CONSUMED_RE1_SOURCES = {
    "sha256:b4424b0b3863b7397712caa0f305ef59964b03784dfcb23e23e0a95a2e746f99": "RCAEval RE1-SS",
    "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4": "RCAEval RE1-OB",
    "sha256:2b33b7ab07198e0d69f229e697bfcef794a656e8db73a1d732142effde17c595": "RCAEval RE1-TT",
}
P113_NEGATIVE_FACTS = {
    "service_top1": "0.312",
    "service_top3": "0.496",
    "fault_accuracy": "0.32",
    "cpu_accuracy": "0.56",
    "mem_accuracy": "0.08",
    "disk_accuracy": "0.28",
    "delay_accuracy": "0.20",
    "loss_accuracy": "0.48",
    "evidence_precision": "1.0",
    "diagnosis_preservation": "1.0",
    "replay_consistency": "1.0",
    "release_qualified": "false",
}
_ALLOWED_PURPOSES = frozenset({"failure_analysis", "model_development", "development_evaluation"})
_ARTIFACT_KEYS = frozenset({"source_hash", "role", "granularity", "purpose", "artifact_hash"})


class P114GovernanceError(ValueError):
    """Raised when P114 lineage or scientific claims violate the frozen contract."""


def build_p114_lineage_ledger() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "consumed_sources": dict(CONSUMED_RE1_SOURCES),
        "p113_negative_facts": dict(P113_NEGATIVE_FACTS),
        "allowed_case_level_purposes": sorted(_ALLOWED_PURPOSES),
        "fresh_system_claim_allowed": False,
        "acceptance_claim": "fresh_case_and_modality_only",
        "action_contract_status": "disabled",
    }
    payload["ledger_hash"] = stable_hash(payload)
    return payload


def validate_p114_lineage_ledger(ledger: Mapping[str, Any]) -> None:
    submitted = str(ledger.get("ledger_hash", ""))
    unhashed = {key: value for key, value in ledger.items() if key != "ledger_hash"}
    if submitted != stable_hash(unhashed):
        raise P114GovernanceError("lineage_ledger_tampered")
    expected = build_p114_lineage_ledger()
    if dict(ledger) != expected:
        raise P114GovernanceError("lineage_ledger_contract_drift")


def validate_p114_development_artifacts(ledger: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]) -> None:
    validate_p114_lineage_ledger(ledger)
    if not artifacts:
        raise P114GovernanceError("missing_development_artifacts")
    consumed = set(CONSUMED_RE1_SOURCES)
    for artifact in artifacts:
        if set(str(key) for key in artifact) != _ARTIFACT_KEYS:
            raise P114GovernanceError("development_artifact_schema_violation")
        source_hash = str(artifact.get("source_hash", ""))
        if source_hash not in consumed:
            raise P114GovernanceError("undeclared_consumed_source")
        if artifact.get("role") != "consumed_development":
            raise P114GovernanceError("consumed_source_role_violation")
        if artifact.get("granularity") not in {"case", "aggregate"}:
            raise P114GovernanceError("invalid_development_granularity")
        if artifact.get("purpose") not in _ALLOWED_PURPOSES:
            raise P114GovernanceError("invalid_development_purpose")
        artifact_hash = str(artifact.get("artifact_hash", ""))
        if not artifact_hash.startswith("sha256:") or len(artifact_hash) != 71:
            raise P114GovernanceError("invalid_development_artifact_hash")
