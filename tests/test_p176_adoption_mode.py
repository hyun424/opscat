from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p176_live_bridge import P176LiveBridgeError, validate_adoption_reviewed_plan_artifacts
from app.services.p176_live_gates import (
    P176LiveGateError,
    build_adoption_baseline_binding,
    validate_adoption_authority_model,
    validate_adoption_baseline_binding,
)
from scripts.run_p176_live_qualification import P176LiveCampaignError, orchestrate_live_campaign, resolve_campaign_mode

ROOT = Path(__file__).resolve().parents[1]
ADOPTION_INFRA = ROOT / "infra" / "gcp" / "p176-adoption"
HASH = "sha256:" + "1" * 64


def test_adoption_baseline_binding_separates_fresh_control_from_p174_workload() -> None:
    binding = build_adoption_baseline_binding(
        run_id="p176-adoption-run-001",
        control_project_id="opscat-p176-admin-adopt01",
        workload_project_id="opscat-p174-lab-base01",
        workload_project_number="123456789012",
        workload_vm_names=["p174-target", "p174-observer"],
        workload_network_self_link="projects/opscat-p174-lab-base01/global/networks/p174-workload-vpc",
        reviewed_adoption_plan_hash=HASH,
        reviewed_adoption_destroy_plan_hash="sha256:" + "2" * 64,
        reviewed_p174_plan_artifact_hash="sha256:" + "3" * 64,
        baseline_inventory_hash="sha256:" + "4" * 64,
    )

    validated = validate_adoption_baseline_binding(binding)
    assert validated["mode"] == "p174_workload_adoption"
    assert validated["control_project_id"] == "opscat-p176-admin-adopt01"
    assert validated["workload_project_id"] == "opscat-p174-lab-base01"
    assert validated["adoption_owns_workload_project"] is False
    assert validated["adoption_owns_workload_network"] is False
    assert validated["adoption_owns_workload_disks"] is False
    assert validated["workload_project_delete_allowed"] is False
    assert validated["binding_hash"] == stable_hash({key: value for key, value in validated.items() if key != "binding_hash"})


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("control_project_id", "opscat-p176-live-newlab1", "adoption_control_project_id_invalid"),
        ("workload_project_id", "opscat-p176-admin-adopt01", "adoption_workload_project_id_invalid"),
        ("workload_project_id", "opscat-p174-prod-main", "adoption_workload_project_forbidden"),
        ("workload_network_self_link", "projects/shared-vpc/global/networks/p174-workload-vpc", "adoption_workload_network_unbound"),
        ("baseline_inventory_hash", "", "baseline_inventory_hash_invalid"),
    ),
)
def test_adoption_baseline_binding_fails_closed_for_unbound_shared_or_missing_baseline(
    field: str,
    value: object,
    error: str,
) -> None:
    binding = build_adoption_baseline_binding(
        run_id="p176-adoption-run-001",
        control_project_id="opscat-p176-admin-adopt01",
        workload_project_id="opscat-p174-lab-base01",
        workload_project_number="123456789012",
        workload_vm_names=["p174-target"],
        workload_network_self_link="projects/opscat-p174-lab-base01/global/networks/p174-workload-vpc",
        reviewed_adoption_plan_hash=HASH,
        reviewed_adoption_destroy_plan_hash="sha256:" + "2" * 64,
        reviewed_p174_plan_artifact_hash="sha256:" + "3" * 64,
        baseline_inventory_hash="sha256:" + "4" * 64,
    )
    tampered = deepcopy(binding)
    tampered[field] = value
    tampered["binding_hash"] = stable_hash({key: item for key, item in tampered.items() if key != "binding_hash"})

    with pytest.raises(P176LiveGateError, match=error):
        validate_adoption_baseline_binding(tampered)


def test_adoption_authority_model_allows_only_control_harness_resources() -> None:
    authority = {
        "mode": "p174_workload_adoption",
        "control_project_id": "opscat-p176-admin-adopt01",
        "workload_project_id": "opscat-p174-lab-base01",
        "harness_control_principal": "p176-adoption-harness@opscat-p176-admin-adopt01.iam.gserviceaccount.com",
        "control_project_iam_roles": ["roles/pubsub.publisher", "roles/logging.logWriter"],
        "workload_project_iam_roles": [],
        "workload_mutation_api_allowlist": [],
        "workload_delete_api_allowlist": [],
        "can_impersonate_p174_runtime": False,
        "can_delete_workload_project": False,
        "can_delete_workload_network": False,
        "can_delete_workload_disks": False,
        "technical_denial_enforced": True,
        "auto_approval_enabled": False,
    }

    assert validate_adoption_authority_model(authority)["adoption_workload_mutation_technically_denied"] is True

    widened = deepcopy(authority)
    widened["workload_project_iam_roles"] = ["roles/compute.admin"]
    with pytest.raises(P176LiveGateError, match="workload_project_iam_roles_must_be_empty"):
        validate_adoption_authority_model(widened)


def test_runner_modes_are_explicit_and_do_not_blend_fresh_lab_with_adoption() -> None:
    assert resolve_campaign_mode("fresh-lab") == "fresh-lab"
    assert resolve_campaign_mode("p174-workload-adoption") == "p174-workload-adoption"

    with pytest.raises(P176LiveCampaignError, match="campaign_mode_invalid"):
        resolve_campaign_mode("shared-prod-adoption")


def test_adoption_runner_fails_closed_when_baseline_binding_is_missing(tmp_path: Path) -> None:
    with pytest.raises(P176LiveCampaignError, match="adoption_baseline_binding_required"):
        orchestrate_live_campaign(run_dir=tmp_path, mode="p174-workload-adoption")


def test_adoption_bridge_binds_baseline_and_reviewed_plan_artifacts(tmp_path: Path) -> None:
    binding = build_adoption_baseline_binding(
        run_id="p176-adoption-run-001",
        control_project_id="opscat-p176-admin-adopt01",
        workload_project_id="opscat-p174-lab-base01",
        workload_project_number="123456789012",
        workload_vm_names=["p174-target"],
        workload_network_self_link="projects/opscat-p174-lab-base01/global/networks/p174-workload-vpc",
        reviewed_adoption_plan_hash=HASH,
        reviewed_adoption_destroy_plan_hash="sha256:" + "2" * 64,
        reviewed_p174_plan_artifact_hash="sha256:" + "3" * 64,
        baseline_inventory_hash="sha256:" + "4" * 64,
    )
    adoption_plan = tmp_path / "p176-adoption.tfplan.json"
    adoption_destroy_plan = tmp_path / "p176-adoption-destroy.tfplan.json"
    p174_plan = tmp_path / "p174-reviewed-plan.json"
    adoption_plan.write_bytes(b"adoption apply plan")
    adoption_destroy_plan.write_bytes(b"adoption destroy plan")
    p174_plan.write_bytes(b"reviewed p174 workload plan")
    binding["reviewed_adoption_plan_hash"] = _file_hash(adoption_plan)
    binding["reviewed_adoption_destroy_plan_hash"] = _file_hash(adoption_destroy_plan)
    binding["reviewed_p174_plan_artifact_hash"] = _file_hash(p174_plan)
    binding["binding_hash"] = stable_hash({key: value for key, value in binding.items() if key != "binding_hash"})

    evidence = validate_adoption_reviewed_plan_artifacts(
        run_dir=tmp_path,
        adoption_baseline_binding=binding,
        reviewed_adoption_plan_artifact_path=adoption_plan,
        reviewed_adoption_destroy_plan_artifact_path=adoption_destroy_plan,
        reviewed_p174_plan_artifact_path=p174_plan,
    )

    assert evidence["adoption_baseline_binding_hash"] == binding["binding_hash"]
    assert evidence["baseline_inventory_hash"] == binding["baseline_inventory_hash"]
    assert evidence["reviewed_adoption_plan_hash"] == _file_hash(adoption_plan)
    assert evidence["reviewed_p174_plan_artifact_hash"] == _file_hash(p174_plan)

    outside = tmp_path.parent / "outside-p174-plan.json"
    outside.write_bytes(b"outside")
    with pytest.raises(P176LiveBridgeError, match="reviewed_p174_plan_artifact_outside_allowed_evidence_root"):
        validate_adoption_reviewed_plan_artifacts(
            run_dir=tmp_path,
            adoption_baseline_binding=binding,
            reviewed_adoption_plan_artifact_path=adoption_plan,
            reviewed_adoption_destroy_plan_artifact_path=adoption_destroy_plan,
            reviewed_p174_plan_artifact_path=outside,
        )


def test_p176_adoption_infra_is_control_only_and_never_owns_p174_workload() -> None:
    files = {path.name for path in ADOPTION_INFRA.iterdir() if path.is_file()}
    assert {"versions.tf", "variables.tf", "main.tf", "outputs.tf", "README.md"} <= files

    terraform = "\n".join(path.read_text(encoding="utf-8") for path in ADOPTION_INFRA.glob("*.tf"))
    assert 'resource "google_project" "p176_adoption_control"' in terraform
    assert "project_id      = var.control_project_id" in terraform
    assert 'name                    = "p176-adoption-control-vpc"' in terraform
    assert 'account_id   = "p176-adoption-harness"' in terraform
    assert 'expected_project_prefix = "opscat-p176-admin-"' in terraform
    assert 'adopted_workload_prefix = "opscat-p174-"' in terraform
    assert 'adoption_owns_workload  = "false"' in terraform
    assert "google_compute_instance" not in terraform
    assert "google_compute_disk" not in terraform
    assert "google_compute_network\" \"p174" not in terraform
    assert "google_project_iam_member\" \"workload" not in terraform
    assert "roles/owner" not in terraform
    assert "roles/editor" not in terraform
    assert "service_account_key" not in terraform
    assert "delete_workload" not in terraform
    assert "shared-vpc" in terraform
    assert "production" in terraform


def _file_hash(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
