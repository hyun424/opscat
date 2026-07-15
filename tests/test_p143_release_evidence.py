from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p143_release_evidence import (
    P143_PRELIMINARY_STATUS,
    P143_READY_STATUS,
    P143_SOURCE_PATHS,
    REQUIRED_LIMITATIONS,
    assemble_p143_final_evidence,
    build_p143_freeze_manifest,
    build_p143_preliminary_evidence,
)
from app.services.p143_runner import p143_release_case_catalog
from tests.test_p143_runner import qualified_p143_matrix

ROOT = Path(__file__).resolve().parents[1]


def p143_profile() -> dict[str, Any]:
    return {"schema_version": "p143.egress_contract_lab_profile.v1", "cases": p143_release_case_catalog()}


def p143_review(manifest: dict[str, Any]) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": "p143.final_implementation_review.v1",
        "reviewer_identity": "p143-independent-code-reviewer",
        "reviewer_agent_id": "019f62b0-c874-73d6-a36e-5e8bc1b19998",
        "reviewer_type": "codex-native-code-reviewer",
        "implementation_identity": "p143-implementation-agent",
        "reviewed_at": "2026-07-15T12:00:00Z",
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_test_spec_sha256": manifest["approved_test_spec_sha256"],
        "reviewed_plan_review_sha256": manifest["plan_review_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": deepcopy(manifest["source_bindings"]),
        "reviewed_dependency_bindings": deepcopy(manifest["dependency_bindings"]),
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    review["review_hash"] = stable_hash(review)
    return review


def rehash_review(review: dict[str, Any]) -> None:
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})


def test_final_evidence_binds_all_frozen_inputs_and_review() -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    assert manifest["approved_plan_sha256"] == "sha256:220b75a4ee32871eed1c2b41b43bbd299c425ea330fc023b73ca5f891668099e"
    assert manifest["approved_test_spec_sha256"] == "sha256:5c7f32cfb563df023544792c0494c842fdc3f566e0725cf9322ccbf0117f19ab"
    assert manifest["dependency_bindings"]["p142_evidence_hash"] == "sha256:3e952653a335da77ca6ce5f9cc7d6dcb9b39299afc7324c016fe8446f5c7f8e6"
    preliminary = build_p143_preliminary_evidence(matrix, manifest)
    assert preliminary["status"] == P143_PRELIMINARY_STATUS
    assert preliminary["final_review_hash"] is None
    review = p143_review(manifest)
    final = assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())
    assert final["status"] == P143_READY_STATUS
    assert final["passed"] == 52
    assert final["final_review_hash"] == review["review_hash"]
    assert P143_SOURCE_PATHS == (
        ".omx/plans/opscat-p143-provider-neutral-egress-contract-lab.md",
        "app/p143_egress_contract_cli.py",
        "app/services/p143_egress_contract_lab.py",
        "app/services/p143_release_evidence.py",
        "app/services/p143_runner.py",
        "docs/operations/p143-implementation-review.md",
        "docs/operations/p143-plan-review.md",
        "docs/operations/p143-test-spec.md",
        "evals/p143/input/egress-contract-lab-profile.json",
        "scripts/run_p143_egress_contract_lab.py",
        "tests/fixtures/p143/__init__.py",
        "tests/fixtures/p143/builders.py",
        "tests/test_p143_egress_contract_cli.py",
        "tests/test_p143_egress_contract_lab.py",
        "tests/test_p143_release_evidence.py",
        "tests/test_p143_runner.py",
    )
    assert REQUIRED_LIMITATIONS == frozenset(
        {
            "provider_neutral_local_projection_lab_only_no_external_delivery",
            "no_credentials_auth_endpoints_urls_dns_proxy_tls_http_provider_sdk_or_environment_config",
            "no_p133_ack_approval_action_remediation_ticket_staging_production_mutation_or_operator_replacement",
            "p142_dependency_validation_does_not_grant_loopback_socket_authority_to_p143",
            "local_execution_provenance_not_cryptographic_attestation",
            "independent_reviewer_identity_not_externally_authenticated",
            "shadow_capability_compatibility_is_not_provider_certification",
        }
    )
    review_doc = (ROOT / "docs/operations/p143-implementation-review.md").read_text(encoding="utf-8")
    assert "019f626a-bfea-72c3-b0c2-cf0d8fda4327" in review_doc
    assert "REQUEST_CHANGES" in review_doc
    verify_script = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
    verify_block = verify_script[verify_script.index("p143_release_profile_tests()") : verify_script.index("p108_prevention_learning_evidence_smoke()")]
    assert "--mode final" in verify_block
    assert "--final-review evals/p143/final-implementation-review.json" in verify_block
    assert "--canonical-matrix evals/p143/output/canonical-matrix.json" in verify_block
    assert "--freeze-manifest evals/p143/output/freeze-manifest.json" in verify_block


def test_final_evidence_rejects_missing_or_forged_independent_review() -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    review["implementation_identity"] = review["reviewer_identity"]
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    with pytest.raises(ValueError, match="identity_not_independent"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())
    review = p143_review(manifest)
    review["limitations"].append("unapproved_extra_limitation")
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    with pytest.raises(ValueError, match="limitations"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())


@pytest.mark.parametrize("finding_value", [False, 0.0])
def test_final_review_rejects_non_integer_zero_findings(finding_value: object) -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    review["findings"]["p1"] = finding_value
    rehash_review(review)

    with pytest.raises(ValueError, match="p143_review_findings_invalid"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())


@pytest.mark.parametrize("field", ["decision", "reviewed_source_hashes"])
def test_final_review_rejects_missing_top_level_fields(field: str) -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    del review[field]
    rehash_review(review)

    with pytest.raises(ValueError, match="p143_review_fields_invalid"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())


def test_final_review_rejects_extra_top_level_field() -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    review["unreviewed_extension"] = "not-authorized"
    rehash_review(review)

    with pytest.raises(ValueError, match="p143_review_fields_invalid"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_final_review_rejects_non_exact_findings_fields(mutation: str) -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    if mutation == "missing":
        del review["findings"]["p3"]
    else:
        review["findings"]["p4"] = 0
    rehash_review(review)

    with pytest.raises(ValueError, match="p143_review_findings_invalid"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())


@pytest.mark.parametrize(
    "agent_id",
    [
        "019f626a-bfea-72c3-a",
        "019F626A-BFEA-72C3-B0C2-CF0D8FDA4327",
        "019f626abfea72c3b0c2cf0d8fda4327",
        "550e8400-e29b-41d4-a716-446655440000",
    ],
)
def test_final_review_rejects_malformed_noncanonical_or_wrong_version_agent_id(agent_id: str) -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    review["reviewer_agent_id"] = agent_id
    rehash_review(review)

    with pytest.raises(ValueError, match="p143_reviewer_agent_id_invalid"):
        assemble_p143_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p143_profile())


def test_final_review_accepts_actual_reviewer_uuid() -> None:
    matrix = qualified_p143_matrix()
    manifest = build_p143_freeze_manifest(project_root=ROOT, profile=p143_profile(), matrix=matrix)
    review = p143_review(manifest)
    review["reviewer_agent_id"] = "019f626a-bfea-72c3-b0c2-cf0d8fda4327"
    rehash_review(review)

    final = assemble_p143_final_evidence(
        matrix,
        manifest=manifest,
        review=review,
        project_root=ROOT,
        profile=p143_profile(),
    )
    assert final["status"] == P143_READY_STATUS
