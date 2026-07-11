from __future__ import annotations

import copy

import pytest

from app.services.p120_governance import (
    P120GovernanceError,
    build_source_manifest,
    build_source_registry,
    validate_exact_zero_authority,
    validate_registry,
    zero_authority_counters,
)


def _manifest() -> dict[str, object]:
    return {
        "source_id": "src-public-1",
        "source_type": "public_benchmark",
        "license_or_usage_basis": "Apache-2.0 research benchmark",
        "collection_method": "offline imported fixture",
        "allowed_use": "cross-system benchmark evaluation only",
        "privacy_redaction_status": "redacted",
        "system_id": "checkout-a",
        "dataset_origin": "public",
        "time_range": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-01T01:00:00Z"},
        "telemetry_modalities": ["metric", "log", "trace"],
        "topology_available": True,
        "labels": None,
        "outcomes": None,
        "actions": None,
        "known_biases": ["small sample"],
        "known_duplicates": [],
        "near_duplicate_fingerprint": "checkout-a-family-1",
        "split_eligible": True,
        "holdout_eligible": True,
        "authority_boundary_receipt": {"receipt": "offline read-only fixture", "read_only": True, "counters": zero_authority_counters()},
        "artifact_hash": "sha256:" + "a" * 64,
        "lineage": {"origin_kind": "observed", "provenance": "public artifact mirror", "generated_lineage_visible": True, "parent_source_ids": []},
        "source_label_fields": ["service", "symptom"],
    }


def test_source_manifest_preserves_nullable_labels_and_builds_registry() -> None:
    manifest = build_source_manifest(_manifest()).to_dict()
    assert manifest["labels"] is None
    assert str(manifest["manifest_hash"]).startswith("sha256:")

    registry = build_source_registry([manifest])
    validate_registry(registry)
    assert registry["source_count"] == 1
    assert registry["authority_counters"] == zero_authority_counters()


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("license_or_usage_basis", "missing_license_or_usage_basis"),
        ("artifact_hash", "missing_artifact_hash"),
        ("authority_boundary_receipt", "missing_authority_boundary_receipt"),
        ("lineage", "missing_lineage"),
    ],
)
def test_source_manifest_rejects_missing_governance_fields(field: str, expected: str) -> None:
    manifest = _manifest()
    manifest.pop(field)
    with pytest.raises(P120GovernanceError, match=expected):
        build_source_manifest(manifest)


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"allowed_use": "production-cluster target export"}, "forbidden_authority_text"),
        ({"lineage": {"origin_kind": "generated", "provenance": "synth", "generated_lineage_visible": False, "parent_source_ids": []}}, "generated_lineage_hidden"),
        ({"authority_boundary_receipt": {"receipt": "bad", "read_only": True, "counters": {**zero_authority_counters(), "secret_material_count": 1}}}, "secret_material_count_nonzero"),
        ({"credential": "api_key=abc"}, "forbidden_authority_field"),
    ],
)
def test_source_manifest_fails_closed_for_authority_and_lineage_red_cases(patch: dict[str, object], expected: str) -> None:
    manifest = {**_manifest(), **patch}
    with pytest.raises(P120GovernanceError, match=expected):
        build_source_manifest(manifest)


def test_registry_detects_tampered_source_manifest_and_nonzero_authority() -> None:
    registry = build_source_registry([_manifest()])
    tampered = copy.deepcopy(registry)
    tampered["sources"][0]["system_id"] = "different"
    with pytest.raises(P120GovernanceError, match="source_manifest_tampered"):
        validate_registry(tampered)

    counters = zero_authority_counters()
    counters["production_mutation_count"] = 1
    with pytest.raises(P120GovernanceError, match="production_mutation_count_nonzero"):
        validate_exact_zero_authority(counters)
