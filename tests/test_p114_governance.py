from __future__ import annotations

import copy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p114_governance import (
    CONSUMED_RE1_SOURCES,
    P113_NEGATIVE_FACTS,
    P114GovernanceError,
    build_p114_lineage_ledger,
    validate_p114_development_artifacts,
    validate_p114_lineage_ledger,
)


def _artifact(source_hash: str, *, granularity: str = "case", purpose: str = "failure_analysis") -> dict[str, str]:
    return {
        "source_hash": source_hash,
        "role": "consumed_development",
        "granularity": granularity,
        "purpose": purpose,
        "artifact_hash": stable_hash({"source_hash": source_hash, "purpose": purpose}),
    }


def test_lineage_ledger_binds_all_consumed_re1_sources_and_p113_negative_facts() -> None:
    ledger = build_p114_lineage_ledger()

    validate_p114_lineage_ledger(ledger)
    assert ledger["consumed_sources"] == CONSUMED_RE1_SOURCES
    assert ledger["p113_negative_facts"] == P113_NEGATIVE_FACTS
    assert ledger["fresh_system_claim_allowed"] is False


def test_lineage_ledger_rejects_tampering_and_json_like_type_drift() -> None:
    ledger = build_p114_lineage_ledger()
    tampered = copy.deepcopy(ledger)
    tampered["p113_negative_facts"]["service_top1"] = "0.60"

    with pytest.raises(P114GovernanceError, match="lineage_ledger_tampered"):
        validate_p114_lineage_ledger(tampered)


def test_development_artifacts_require_declared_consumed_lineage_and_bounded_purpose() -> None:
    ledger = build_p114_lineage_ledger()
    source_hash = next(iter(CONSUMED_RE1_SOURCES))

    validate_p114_development_artifacts(ledger, [_artifact(source_hash)])

    with pytest.raises(P114GovernanceError, match="undeclared_consumed_source"):
        validate_p114_development_artifacts(ledger, [_artifact("sha256:" + "f" * 64)])
    with pytest.raises(P114GovernanceError, match="invalid_development_purpose"):
        validate_p114_development_artifacts(ledger, [_artifact(source_hash, purpose="blind_release")])


def test_consumed_case_level_material_cannot_claim_blind_or_release_role() -> None:
    ledger = build_p114_lineage_ledger()
    source_hash = next(iter(CONSUMED_RE1_SOURCES))
    artifact = {**_artifact(source_hash), "role": "fresh_blind"}

    with pytest.raises(P114GovernanceError, match="consumed_source_role_violation"):
        validate_p114_development_artifacts(ledger, [artifact])


def test_artifact_schema_rejects_smuggled_case_or_truth_fields() -> None:
    ledger = build_p114_lineage_ledger()
    source_hash = next(iter(CONSUMED_RE1_SOURCES))
    artifact = {**_artifact(source_hash), "root_service": "hidden"}

    with pytest.raises(P114GovernanceError, match="development_artifact_schema_violation"):
        validate_p114_development_artifacts(ledger, [artifact])
