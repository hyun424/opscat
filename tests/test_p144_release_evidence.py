from __future__ import annotations

import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p144_release_evidence import (
    P144_PRELIMINARY_STATUS,
    P144_READY_STATUS,
    P144_SOURCE_PATHS,
    REQUIRED_LIMITATIONS,
    assemble_p144_final_evidence,
    build_p144_freeze_manifest,
    build_p144_preliminary_evidence,
)
from app.services.p144_runner import p144_release_case_catalog
from scripts import run_p144_provider_adapter_lab as release_script
from tests.test_p144_runner import qualified_p144_matrix

ROOT = Path(__file__).resolve().parents[1]


def p144_profile() -> dict[str, Any]:
    return {"schema_version": "p144.provider_adapter_lab_profile.v1", "cases": p144_release_case_catalog()}


def p144_review(manifest: dict[str, Any]) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": "p144.final_implementation_review.v1",
        "reviewer_identity": "p144-independent-code-reviewer",
        "reviewer_agent_id": "019f632a-b9d5-7643-b8e9-08804917f8f2",
        "reviewer_type": "codex-native-code-reviewer",
        "implementation_identity": "p144-implementation-agent",
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


def test_final_evidence_binds_freeze_review_dependencies_and_limitations() -> None:
    matrix = qualified_p144_matrix()
    manifest = build_p144_freeze_manifest(project_root=ROOT, profile=p144_profile(), matrix=matrix)
    preliminary = build_p144_preliminary_evidence(matrix, manifest)
    assert preliminary["final_review_hash"] is None
    assert manifest["approved_plan_sha256"] == "sha256:592153aec6310429b4ddd728b25633d2553b07682513463d23641ed1fdd9e886"
    assert manifest["approved_test_spec_sha256"] == "sha256:7266e0546023b69b34fab6b9c548316e546f71a9001cd2be71e7caa9aa60969f"
    assert manifest["dependency_bindings"]["p143_evidence_hash"] == "sha256:0a6aacb837e931858e78db82e41a8273b39d145070a4f95f4c67a0f4cbfe1a72"
    assert manifest["dependency_bindings"]["p142_evidence_hash"] == "sha256:ac3830fcad5a8919d98b53bcadd39679ad26f6b3ad0890d24e4616b8993d57e6"
    assert manifest["dependency_bindings"]["p133_dependency"] == {
        "p133_status": "p133_local_deadman_outbox_qualified",
        "p133_evidence_hash": "sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f",
    }
    final = assemble_p144_final_evidence(matrix, manifest=manifest, review=p144_review(manifest), project_root=ROOT, profile=p144_profile())
    assert final["status"] == P144_READY_STATUS
    assert final["status"] == "p144_numeric_loopback_provider_adapter_qualified"
    assert final["passed"] == 64
    assert set(final["limitations"]) == REQUIRED_LIMITATIONS
    assert P144_SOURCE_PATHS[-4:] == (
        "tests/fixtures/p144/builders.py",
        "tests/test_p144_provider_adapter_cli.py",
        "tests/test_p144_provider_adapter_lab.py",
        "tests/test_p144_release_evidence.py",
        "tests/test_p144_runner.py",
    )[-4:]


def test_final_review_rejects_non_integer_zero_findings() -> None:
    matrix = qualified_p144_matrix()
    manifest = build_p144_freeze_manifest(project_root=ROOT, profile=p144_profile(), matrix=matrix)
    review = p144_review(manifest)
    review["findings"]["p2"] = False
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    with pytest.raises(ValueError, match="findings"):
        assemble_p144_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p144_profile())


def test_final_review_rejects_missing_or_forged_bindings() -> None:
    matrix = qualified_p144_matrix()
    manifest = build_p144_freeze_manifest(project_root=ROOT, profile=p144_profile(), matrix=matrix)
    review = p144_review(manifest)
    review["reviewed_matrix_hash"] = stable_hash({"forged": "matrix"})
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    with pytest.raises(ValueError, match="binding"):
        assemble_p144_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p144_profile())


def test_required_limitations_are_exact_approved_eight() -> None:
    assert REQUIRED_LIMITATIONS == frozenset(
        {
            "numeric_loopback_provider_adapter_conformance_only_no_external_delivery",
            "no_credentials_auth_dns_tls_proxy_provider_sdk_or_environment_config",
            "receiver_address_process_owned_not_configurable_or_persisted_as_authority",
            "provider_shaped_response_is_local_fixture_evidence_not_certification",
            "indeterminate_post_send_state_requires_review_and_never_auto_retries",
            "no_p133_ack_approval_action_remediation_ticket_staging_production_mutation_or_operator_replacement",
            "local_execution_provenance_not_cryptographic_attestation",
            "independent_reviewer_identity_not_externally_authenticated",
        }
    )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("reviewer_type", "human", "reviewer_type"),
        ("reviewer_identity", "", "reviewer_identity"),
        ("reviewer_identity", "x" * 129, "reviewer_identity"),
        ("reviewer_identity", " reviewer", "reviewer_identity"),
        ("reviewer_identity", "reviewer\nidentity", "reviewer_identity"),
        ("implementation_identity", "", "implementer_identity"),
        ("implementation_identity", "x" * 129, "implementer_identity"),
        ("implementation_identity", "implementer ", "implementer_identity"),
        ("reviewed_at", "2026-07-15T12:00:00+00:00", "timestamp"),
        ("reviewed_at", "2026-07-15T12:00:00.000Z", "timestamp"),
        ("reviewer_agent_id", "019F632A-B9D5-7643-B8E9-08804917F8F2", "agent_id"),
        ("reviewer_agent_id", "019f632ab9d57643b8e908804917f8f2", "agent_id"),
        ("reviewer_agent_id", "550e8400-e29b-41d4-a716-446655440000", "agent_id"),
    ],
)
def test_final_review_rejects_noncanonical_identity_type_uuid_or_utc(field: str, value: str, error: str) -> None:
    matrix = qualified_p144_matrix()
    manifest = build_p144_freeze_manifest(project_root=ROOT, profile=p144_profile(), matrix=matrix)
    review = p144_review(manifest)
    review[field] = value
    rehash_review(review)
    with pytest.raises(ValueError, match=error):
        assemble_p144_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p144_profile())


def test_final_review_rejects_duplicate_or_substituted_limitations() -> None:
    matrix = qualified_p144_matrix()
    manifest = build_p144_freeze_manifest(project_root=ROOT, profile=p144_profile(), matrix=matrix)
    for limitations in (
        sorted(REQUIRED_LIMITATIONS)[:-1],
        [*sorted(REQUIRED_LIMITATIONS), sorted(REQUIRED_LIMITATIONS)[0]],
        [*sorted(REQUIRED_LIMITATIONS)[:-1], "substituted"],
    ):
        review = p144_review(manifest)
        review["limitations"] = limitations
        rehash_review(review)
        with pytest.raises(ValueError, match="limitations"):
            assemble_p144_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p144_profile())


def test_release_runner_is_strict_two_phase_and_final_preserves_frozen_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = tmp_path / "profile.json"
    output_dir = tmp_path / "preliminary"
    profile_path.write_text(__import__("json").dumps(p144_profile(), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    monkeypatch.setattr(release_script, "run_p144_preliminary_matrix", lambda _root: qualified_p144_matrix())

    matrix_path = output_dir / "canonical-matrix.json"
    freeze_path = output_dir / "freeze-manifest.json"
    assert (
        release_script.main(
            [
                "--mode",
                "preliminary",
                "--profile",
                str(profile_path),
                "--canonical-matrix",
                str(matrix_path),
                "--freeze-manifest",
                str(freeze_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    preliminary = release_script._read_json(output_dir / "release-evidence.json")
    assert preliminary["status"] == P144_PRELIMINARY_STATUS
    assert preliminary["final_review_hash"] is None
    matrix_before = matrix_path.read_bytes()
    freeze_before = freeze_path.read_bytes()

    missing_review = tmp_path / "missing-review.json"
    assert (
        release_script.main(
            [
                "--mode",
                "final",
                "--profile",
                str(profile_path),
                "--canonical-matrix",
                str(matrix_path),
                "--freeze-manifest",
                str(freeze_path),
                "--final-review",
                str(missing_review),
                "--output-dir",
                str(tmp_path / "final"),
            ]
        )
        == 1
    )
    assert not missing_review.exists()
    assert matrix_path.read_bytes() == matrix_before
    assert freeze_path.read_bytes() == freeze_before


def test_pyproject_exposes_p144_console_script() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["opscat-provider-adapter-lab"] == "app.p144_provider_adapter_cli:main"


def test_implementation_review_records_remediation_and_final_independent_approval() -> None:
    review = (ROOT / "docs/operations/p144-implementation-review.md").read_text(encoding="utf-8")
    assert "REQUEST_CHANGES" in review
    assert all(item in review for item in ("P0: 1", "P1: 5", "P2: 2"))
    assert "Decision: `APPROVE`" in review
    assert "Findings: `P0=0, P1=0, P2=0, P3=0`" in review
    assert "pending independent re-review" not in review


def test_verify_profile_reads_frozen_inputs_and_writes_final_to_temporary_output() -> None:
    verify = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
    block = verify.split("p144_release_profile_tests() {", 1)[1].split("\n}", 1)[0]
    assert "--canonical-matrix evals/p144/output/canonical-matrix.json" in block
    assert "--freeze-manifest evals/p144/output/freeze-manifest.json" in block
    assert '--output-dir "$VERIFY_TMPDIR/p144-release"' in block
    assert "--output-dir evals/p144/output" not in block
