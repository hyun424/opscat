from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p147_p152_contracts import file_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_evaluator import SAFETY_COUNTER_KEYS
from app.services.p176_evidence import append_evidence_record
from app.services.p176_release import (
    LIMITATIONS,
    SOURCE_PATHS,
    P176ReleaseError,
    assemble_release_evidence,
    build_release_artifacts,
    validate_release_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
SAFETY_ZERO = {key: 0 for key in SAFETY_COUNTER_KEYS}
SUBORDINATE_STATUS = "p176_disposable_gcp_live_lab_evidence_ready"


def _outcomes() -> list[dict[str, object]]:
    return [
        {
            "episode_id": episode["episode_id"],
            "incident_detected": True,
            "diagnosis_correct": True,
            "routing_correct": True,
            "recovery_verified": True,
            "collateral_impact": False,
            "citation_supported": True,
            "human_required": True,
            "mutation_executed": False,
        }
        for episode in generate_p176_campaign()["episodes"]
    ]


def _healthy_results() -> list[dict[str, object]]:
    return [
        {"window_id": window["window_id"], "false_alert": False, "false_action": False}
        for window in generate_p176_campaign()["healthy_windows"]
    ]


def _ledger(ledger_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, source_class in enumerate(
        (
            "metrics",
            "logs",
            "traces",
            "deploy_history",
            "host_state",
            "container_state",
            "topology",
            "dependency_health",
        ),
        start=1,
    ):
        records.append(
            append_evidence_record(
                previous=records[-1] if records else None,
                ledger_name=ledger_name,
                source_class=source_class,
                source_id=f"{ledger_name}/{source_class}",
                observed_at=f"2026-07-18T00:{index:02d}:00Z",
                received_at=f"2026-07-18T00:{index:02d}:30Z",
                freshness_bound_seconds=300,
                content_hash=stable_hash({"ledger": ledger_name, "seq": index}),
                redaction_receipt_hash=stable_hash({"redacted": ledger_name, "seq": index}),
                summary={"signal": f"redacted_{source_class}_bucket"},
                evaluator_context_hash=(
                    stable_hash({"sealed": ledger_name, "seq": index}) if ledger_name == "evaluator_only" else None
                ),
            )
        )
    return records


def _review(report: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    review = {
        "schema_version": "p176.final_implementation_review.v1",
        "phase": "p176",
        "decision": "approve",
        "reviewed_at": "2026-07-18T09:00:00Z",
        "writer_id": "019f7486-f477-73d2-90ed-67d31911757a",
        "reviewer_id": "019f7486-f68b-77a3-adc1-20d19eecf344",
        "reviewer_identity": "p176-independent-release-reviewer",
        "review_source": "codex_native_subagent",
        "reviewed_report_hash": report["report_hash"],
        "reviewed_freeze_manifest_hash": freeze["manifest_hash"],
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": list(LIMITATIONS),
        "review_hash": "",
    }
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    return review


def _teardown_proof() -> dict[str, Any]:
    proof = {
        "schema_version": "p176.live_teardown_proof.v1",
        "phase": "p176",
        "run_id": "p176-live-20260718T000000Z",
        "reviewed_teardown_plan_hash": stable_hash({"reviewed": "teardown"}),
        "reviewed_apply_started_at": "2026-07-18T00:00:00Z",
        "collection_started_at": "2026-07-18T00:00:00Z",
        "collection_completed_at": "2026-07-18T00:00:00Z",
        "terminal_stop_at": "2026-07-18T00:00:00Z",
        "teardown_started_at": "2026-07-18T00:30:00Z",
        "teardown_completed_at": "2026-07-18T00:40:00Z",
        "concurrency_plan_proven": True,
        "remaining_non_billing_resource_count": 0,
        "residual_effect_count": 0,
        "final_cost_snapshot_hash": stable_hash({"cost": 0}),
        "teardown_hash": "",
    }
    proof["teardown_hash"] = stable_hash({key: value for key, value in proof.items() if key != "teardown_hash"})
    return proof


def _terraform_plan_artifact_bindings(teardown_proof: dict[str, Any]) -> dict[str, str]:
    return {
        "reviewed_apply_plan_artifact_name": "reviewed_lab_apply_plan",
        "reviewed_apply_plan_hash": stable_hash({"reviewed": "apply"}),
        "reviewed_teardown_plan_artifact_name": "reviewed_lab_destroy_plan",
        "reviewed_teardown_plan_hash": teardown_proof["reviewed_teardown_plan_hash"],
        "reviewed_cost_cutoff_apply_plan_artifact_name": "reviewed_cost_cutoff_apply_plan",
        "reviewed_cost_cutoff_apply_plan_hash": stable_hash({"reviewed": "cost-cutoff-apply"}),
        "reviewed_cost_cutoff_destroy_plan_artifact_name": "reviewed_cost_cutoff_destroy_plan",
        "reviewed_cost_cutoff_destroy_plan_hash": stable_hash({"reviewed": "cost-cutoff-destroy"}),
    }


def _billing_report() -> dict[str, Any]:
    project_id = "opscat-p176-live-" + "test01"
    billing_account_id = "-".join(("ABCDEF", "123456", "789ABC"))
    budget_resource_name = f"billingAccounts/{billing_account_id}/budgets/p176-live-test-budget"
    report = {
        "schema_version": "p176.live_billing_report.v1",
        "phase": "p176",
        "run_id": "p176-live-20260718T000000Z",
        "project_id": project_id,
        "billing_account_id": billing_account_id,
        "budget_resource_name": budget_resource_name,
        "poll_interval_seconds": 300,
        "max_poll_age_seconds": 600,
        "budget_alert_amount_krw": 30000,
        "hard_stop_amount_krw": 27000,
        "forecast_uncertainty_margin": 1.15,
        "poll_count": 12,
        "stale_poll_count": 0,
        "latest_poll_at": "2026-07-18T00:35:00Z",
        "latest_actual_cost_krw": 12000,
        "latest_forecast_cost_krw": 15000,
        "stop_triggered": False,
        "latest_provider_poll_receipt": {
            "schema_version": "p176.live_billing_poll_receipt.v1",
            "source": "gcp_cloud_billing_api",
            "run_id": "p176-live-20260718T000000Z",
            "project_id": project_id,
            "billing_account_id": billing_account_id,
            "budget_resource_name": budget_resource_name,
            "polled_at": "2026-07-18T00:35:00Z",
            "actual_cost_krw": 12000,
            "forecast_cost_krw": 15000,
            "provider_response_hash": stable_hash({"provider": "billing", "poll": 12}),
            "receipt_hash": "",
        },
        "billing_report_hash": "",
    }
    _rehash_billing(report)
    return report


def _live_manifests(
    *,
    outcomes: list[dict[str, object]],
    healthy_results: list[dict[str, object]],
    safety_counters: dict[str, int],
    agent_visible_ledger: list[dict[str, Any]],
    evaluator_only_ledger: list[dict[str, Any]],
    billing_report: dict[str, Any],
    teardown_proof: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign = generate_p176_campaign()
    input_manifest_hash = file_hash(ROOT / "evals/p176/input/manifest.json")
    agent_chain = stable_hash([record["record_hash"] for record in agent_visible_ledger])
    evaluator_chain = stable_hash([record["record_hash"] for record in evaluator_only_ledger])
    strata_hash = stable_hash(
        {
            "episode_ids": [episode["episode_id"] for episode in campaign["episodes"]],
            "window_ids": [window["window_id"] for window in campaign["healthy_windows"]],
            "denominators": campaign["denominators"],
        }
    )
    runtime_collection_receipt_hash = stable_hash({"receipt": "runtime-collection"})
    runtime_finalization_receipt_hash = stable_hash({"receipt": "runtime-finalization"})
    live_artifact_manifest = {
        "schema_version": "p176.live_artifact_manifest.v1",
        "phase": "p176",
        "run_id": teardown_proof["run_id"],
        "subordinate_status": SUBORDINATE_STATUS,
        "campaign_hash": campaign["campaign_hash"],
        "input_manifest_hash": input_manifest_hash,
        "project_binding_hash": stable_hash({"project": "opscat-p176-live-test"}),
        "project_id": billing_report["project_id"],
        "billing_account_id": billing_report["billing_account_id"],
        "budget_resource_name": billing_report["budget_resource_name"],
        "billing_poll_receipt_hash": billing_report["latest_provider_poll_receipt"]["receipt_hash"],
        "fault_registry_hash": stable_hash({"faults": 30, "cleanup": "cleanup_fault_lease"}),
        "episode_observations_hash": stable_hash({"episodes": len(outcomes)}),
        "healthy_window_observations_hash": stable_hash({"windows": len(healthy_results)}),
        "agent_visible_ledger_chain_hash": agent_chain,
        "evaluator_only_ledger_chain_hash": evaluator_chain,
        "live_safety_hash": stable_hash({"live_safety": "zero"}),
        "billing_report_hash": billing_report["billing_report_hash"],
        "teardown_proof_hash": teardown_proof["teardown_hash"],
        "strata_reconciliation_hash": strata_hash,
        "runtime_collection_receipt_hash": runtime_collection_receipt_hash,
        "runtime_finalization_receipt_hash": runtime_finalization_receipt_hash,
        "terraform_plan_artifact_bindings": _terraform_plan_artifact_bindings(teardown_proof),
        "manifest_hash": "",
    }
    live_artifact_manifest["manifest_hash"] = stable_hash(
        {key: value for key, value in live_artifact_manifest.items() if key != "manifest_hash"}
    )
    release_inputs_manifest = {
        "schema_version": "p176.live_release_inputs_manifest.v1",
        "phase": "p176",
        "run_id": teardown_proof["run_id"],
        "subordinate_status": SUBORDINATE_STATUS,
        "campaign_hash": campaign["campaign_hash"],
        "input_manifest_hash": input_manifest_hash,
        "live_artifact_manifest_hash": live_artifact_manifest["manifest_hash"],
        "outcomes_hash": stable_hash(outcomes),
        "healthy_results_hash": stable_hash(healthy_results),
        "canonical_safety_counters_hash": stable_hash(safety_counters),
        "agent_visible_ledger_chain_hash": agent_chain,
        "evaluator_only_ledger_chain_hash": evaluator_chain,
        "strata_reconciliation_hash": strata_hash,
        "runtime_collection_receipt_hash": runtime_collection_receipt_hash,
        "runtime_finalization_receipt_hash": runtime_finalization_receipt_hash,
        "build_release_artifacts_target": "app.services.p176_release.build_release_artifacts",
        "terraform_plan_artifact_bindings": _terraform_plan_artifact_bindings(teardown_proof),
        "manifest_hash": "",
    }
    release_inputs_manifest["manifest_hash"] = stable_hash(
        {key: value for key, value in release_inputs_manifest.items() if key != "manifest_hash"}
    )
    return release_inputs_manifest, live_artifact_manifest


def _live_inputs() -> dict[str, Any]:
    outcomes = _outcomes()
    healthy_results = _healthy_results()
    agent_visible_ledger = _ledger("agent_visible")
    evaluator_only_ledger = _ledger("evaluator_only")
    billing_report = _billing_report()
    teardown_proof = _teardown_proof()
    release_inputs_manifest, live_artifact_manifest = _live_manifests(
        outcomes=outcomes,
        healthy_results=healthy_results,
        safety_counters=SAFETY_ZERO,
        agent_visible_ledger=agent_visible_ledger,
        evaluator_only_ledger=evaluator_only_ledger,
        billing_report=billing_report,
        teardown_proof=teardown_proof,
    )
    return {
        "outcomes": outcomes,
        "healthy_results": healthy_results,
        "safety_counters": SAFETY_ZERO,
        "agent_visible_ledger": agent_visible_ledger,
        "evaluator_only_ledger": evaluator_only_ledger,
        "release_inputs_manifest": release_inputs_manifest,
        "live_artifact_manifest": live_artifact_manifest,
        "billing_report": billing_report,
        "teardown_proof": teardown_proof,
    }


def test_live_lab_evidence_is_subordinate_and_bound_to_existing_release_claim() -> None:
    inputs = _live_inputs()

    artifacts = build_release_artifacts(project_root=ROOT, **inputs)
    release = assemble_release_evidence(
        project_root=ROOT,
        report=artifacts["report"],
        denominator_report=artifacts["denominator_report"],
        representativeness_report=artifacts["representativeness_report"],
        freeze_manifest=artifacts["freeze_manifest"],
        final_review=_review(artifacts["report"], artifacts["freeze_manifest"]),
    )
    validated = validate_release_evidence(
        release,
        project_root=ROOT,
        report=artifacts["report"],
        denominator_report=artifacts["denominator_report"],
        representativeness_report=artifacts["representativeness_report"],
        freeze_manifest=artifacts["freeze_manifest"],
        final_review=_review(artifacts["report"], artifacts["freeze_manifest"]),
    )

    live = release["live_lab_evidence"]
    assert live["subordinate_status"] == SUBORDINATE_STATUS
    assert live["evaluator_maximum_claim"] == "multi_service_staging_fault_qualified"
    assert live["release_status"] == "p176_multi_service_staging_fault_qualified"
    assert live["release_claim"] == "multi_service_staging_fault_campaign_qualified_from_supplied_observed_outcomes"
    assert live["release_claim_path"] == "existing_p176_release"
    assert live["separate_live_release_claim_count"] == 0
    assert live["teardown_proof_hash"] == inputs["teardown_proof"]["teardown_hash"]
    plan_bindings = inputs["release_inputs_manifest"]["terraform_plan_artifact_bindings"]
    assert plan_bindings == inputs["live_artifact_manifest"]["terraform_plan_artifact_bindings"]
    assert set(plan_bindings) == {
        "reviewed_apply_plan_artifact_name",
        "reviewed_apply_plan_hash",
        "reviewed_teardown_plan_artifact_name",
        "reviewed_teardown_plan_hash",
        "reviewed_cost_cutoff_apply_plan_artifact_name",
        "reviewed_cost_cutoff_apply_plan_hash",
        "reviewed_cost_cutoff_destroy_plan_artifact_name",
        "reviewed_cost_cutoff_destroy_plan_hash",
    }
    required_sources = {
        "app/services/p176_live_bridge.py",
        "app/services/p176_live_gates.py",
        "app/services/p176_runtime_bridge.py",
        "scripts/run_p176_live_runtime_bridge.py",
        "scripts/run_p176_live_qualification.py",
        "infra/gcp/p176-live/.terraform.lock.hcl",
        "infra/gcp/p176-live/README.md",
        "infra/gcp/p176-live/deploy.sh",
        "infra/gcp/p176-live/destroy.sh",
        "infra/gcp/p176-live/main.tf",
        "infra/gcp/p176-live/observer-startup.sh",
        "infra/gcp/p176-live/outputs.tf",
        "infra/gcp/p176-live/preflight.sh",
        "infra/gcp/p176-live/runtime-iap.sh",
        "infra/gcp/p176-live/target-startup.sh",
        "infra/gcp/p176-live/terraform.tfvars.example",
        "infra/gcp/p176-live/terraform.tfvars.template",
        "infra/gcp/p176-live/variables.tf",
        "infra/gcp/p176-live/verify-apply-plan.jq",
        "infra/gcp/p176-live/verify-destroy-plan.jq",
        "infra/gcp/p176-live/versions.tf",
        "infra/gcp/p176-cost-cutoff/.terraform.lock.hcl",
        "infra/gcp/p176-cost-cutoff/README.md",
        "infra/gcp/p176-cost-cutoff/deploy.sh",
        "infra/gcp/p176-cost-cutoff/destroy.sh",
        "infra/gcp/p176-cost-cutoff/main.tf",
        "infra/gcp/p176-cost-cutoff/outputs.tf",
        "infra/gcp/p176-cost-cutoff/preflight.sh",
        "infra/gcp/p176-cost-cutoff/terraform.tfvars.example",
        "infra/gcp/p176-cost-cutoff/terraform.tfvars.template",
        "infra/gcp/p176-cost-cutoff/variables.tf",
        "infra/gcp/p176-cost-cutoff/verify-apply-plan.jq",
        "infra/gcp/p176-cost-cutoff/verify-destroy-plan.jq",
        "infra/gcp/p176-cost-cutoff/versions.tf",
        "lab/p176/live/docker-compose.yml",
        "lab/p176/live/docker-compose.runtime.yml",
        "lab/p176/live/fault_controller.py",
        "lab/p176/live/service_stub.py",
        "lab/p176/live/telemetry_collector.py",
        "lab/p176/live/topology.json",
        "lab/p176/observer/docker-compose.yml",
        "tests/test_p176_live_bridge.py",
        "tests/test_p176_live_campaign.py",
        "tests/test_p176_cost_cutoff.py",
        "tests/test_p176_live_fault_controller.py",
        "tests/test_p176_live_gates.py",
        "tests/test_p176_live_infra_plan.py",
        "tests/test_p176_live_release.py",
        "tests/test_p176_live_runtime_bridge.py",
        "tests/test_p176_live_topology.py",
        "tests/test_p176_runtime_iap_script.py",
    }
    assert required_sources.issubset(SOURCE_PATHS)
    assert validated["qualified"] is True


def test_live_lab_validation_requires_exact_four_plan_binding_keyset() -> None:
    inputs = _live_inputs()
    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    inputs["release_inputs_manifest"].pop("terraform_plan_artifact_bindings")
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    with pytest.raises(P176ReleaseError, match="live_release_inputs_manifest_keyset_invalid"):
        build_release_artifacts(project_root=ROOT, **inputs)

    inputs = _live_inputs()
    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    bindings = deepcopy(inputs["release_inputs_manifest"]["terraform_plan_artifact_bindings"])
    bindings.pop("reviewed_cost_cutoff_destroy_plan_hash")
    inputs["release_inputs_manifest"]["terraform_plan_artifact_bindings"] = bindings
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    inputs["live_artifact_manifest"] = deepcopy(inputs["live_artifact_manifest"])
    inputs["live_artifact_manifest"]["terraform_plan_artifact_bindings"] = bindings
    inputs["live_artifact_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["live_artifact_manifest"].items() if key != "manifest_hash"}
    )
    inputs["release_inputs_manifest"]["live_artifact_manifest_hash"] = inputs["live_artifact_manifest"]["manifest_hash"]
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    with pytest.raises(P176ReleaseError, match="terraform_plan_artifact_bindings_keyset_invalid"):
        build_release_artifacts(project_root=ROOT, **inputs)


def test_live_lab_validation_fails_closed_on_live_manifest_or_billing_teardown_drift() -> None:
    inputs = _live_inputs()
    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    inputs["release_inputs_manifest"]["build_release_artifacts_target"] = "app.services.p176_live_release.build_release_artifacts"
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    with pytest.raises(P176ReleaseError, match="live_release_target_invalid"):
        build_release_artifacts(project_root=ROOT, **inputs)

    inputs = _live_inputs()
    inputs["teardown_proof"] = deepcopy(inputs["teardown_proof"])
    inputs["teardown_proof"]["remaining_non_billing_resource_count"] = 1
    inputs["teardown_proof"]["teardown_hash"] = stable_hash(
        {key: value for key, value in inputs["teardown_proof"].items() if key != "teardown_hash"}
    )
    inputs["live_artifact_manifest"] = deepcopy(inputs["live_artifact_manifest"])
    inputs["live_artifact_manifest"]["teardown_proof_hash"] = inputs["teardown_proof"]["teardown_hash"]
    inputs["live_artifact_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["live_artifact_manifest"].items() if key != "manifest_hash"}
    )
    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    inputs["release_inputs_manifest"]["live_artifact_manifest_hash"] = inputs["live_artifact_manifest"]["manifest_hash"]
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    with pytest.raises(P176ReleaseError, match="live_teardown_not_clean"):
        build_release_artifacts(project_root=ROOT, **inputs)

    inputs = _live_inputs()
    inputs["billing_report"] = None
    with pytest.raises(P176ReleaseError, match="live_evidence_incomplete"):
        build_release_artifacts(project_root=ROOT, **inputs)

    inputs = _live_inputs()
    inputs["billing_report"] = deepcopy(inputs["billing_report"])
    inputs["billing_report"]["stale_poll_count"] = 1
    inputs["billing_report"]["billing_report_hash"] = stable_hash(
        {key: value for key, value in inputs["billing_report"].items() if key != "billing_report_hash"}
    )
    inputs["live_artifact_manifest"] = deepcopy(inputs["live_artifact_manifest"])
    inputs["live_artifact_manifest"]["billing_report_hash"] = inputs["billing_report"]["billing_report_hash"]
    inputs["live_artifact_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["live_artifact_manifest"].items() if key != "manifest_hash"}
    )
    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    inputs["release_inputs_manifest"]["live_artifact_manifest_hash"] = inputs["live_artifact_manifest"]["manifest_hash"]
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    with pytest.raises(P176ReleaseError, match="live_billing_report_invalid"):
        build_release_artifacts(project_root=ROOT, **inputs)

    inputs = _live_inputs()
    terminal_stop = datetime(2026, 7, 18, 0, 0, tzinfo=UTC)
    inputs["billing_report"] = deepcopy(inputs["billing_report"])
    inputs["billing_report"]["latest_poll_at"] = "2026-07-18T01:05:00Z"
    _rehash_billing(inputs["billing_report"])
    inputs["teardown_proof"] = deepcopy(inputs["teardown_proof"])
    inputs["teardown_proof"]["teardown_started_at"] = "2026-07-18T01:00:01Z"
    inputs["teardown_proof"]["teardown_completed_at"] = "2026-07-18T01:10:01Z"
    inputs["teardown_proof"]["teardown_hash"] = stable_hash(
        {key: value for key, value in inputs["teardown_proof"].items() if key != "teardown_hash"}
    )
    inputs["live_artifact_manifest"] = deepcopy(inputs["live_artifact_manifest"])
    inputs["live_artifact_manifest"]["billing_report_hash"] = inputs["billing_report"]["billing_report_hash"]
    inputs["live_artifact_manifest"]["billing_poll_receipt_hash"] = inputs["billing_report"][
        "latest_provider_poll_receipt"
    ]["receipt_hash"]
    inputs["live_artifact_manifest"]["teardown_proof_hash"] = inputs["teardown_proof"]["teardown_hash"]
    inputs["live_artifact_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["live_artifact_manifest"].items() if key != "manifest_hash"}
    )
    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    inputs["release_inputs_manifest"]["live_artifact_manifest_hash"] = inputs["live_artifact_manifest"]["manifest_hash"]
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )
    with pytest.raises(P176ReleaseError, match="live_teardown_proof_invalid"):
        build_release_artifacts(project_root=ROOT, terminal_stop_at=terminal_stop, **inputs)


def test_live_lab_validation_rejects_cross_run_replayed_proofs() -> None:
    inputs = _live_inputs()
    replayed_run_id = f"{inputs['release_inputs_manifest']['run_id']}-replayed"

    inputs["billing_report"] = deepcopy(inputs["billing_report"])
    inputs["billing_report"]["run_id"] = replayed_run_id
    _rehash_billing(inputs["billing_report"])

    inputs["teardown_proof"] = deepcopy(inputs["teardown_proof"])
    inputs["teardown_proof"]["run_id"] = replayed_run_id
    inputs["teardown_proof"]["teardown_hash"] = stable_hash(
        {key: value for key, value in inputs["teardown_proof"].items() if key != "teardown_hash"}
    )

    inputs["live_artifact_manifest"] = deepcopy(inputs["live_artifact_manifest"])
    inputs["live_artifact_manifest"]["run_id"] = replayed_run_id
    inputs["live_artifact_manifest"]["billing_report_hash"] = inputs["billing_report"]["billing_report_hash"]
    inputs["live_artifact_manifest"]["billing_poll_receipt_hash"] = inputs["billing_report"][
        "latest_provider_poll_receipt"
    ]["receipt_hash"]
    inputs["live_artifact_manifest"]["teardown_proof_hash"] = inputs["teardown_proof"]["teardown_hash"]
    inputs["live_artifact_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["live_artifact_manifest"].items() if key != "manifest_hash"}
    )

    inputs["release_inputs_manifest"] = deepcopy(inputs["release_inputs_manifest"])
    inputs["release_inputs_manifest"]["live_artifact_manifest_hash"] = inputs["live_artifact_manifest"]["manifest_hash"]
    inputs["release_inputs_manifest"]["manifest_hash"] = stable_hash(
        {key: value for key, value in inputs["release_inputs_manifest"].items() if key != "manifest_hash"}
    )

    with pytest.raises(P176ReleaseError, match="live_manifest_binding_mismatch:run_id"):
        build_release_artifacts(project_root=ROOT, **inputs)


def _rehash_billing(report: dict[str, Any]) -> None:
    receipt = report["latest_provider_poll_receipt"]
    receipt["run_id"] = report["run_id"]
    receipt["project_id"] = report["project_id"]
    receipt["billing_account_id"] = report["billing_account_id"]
    receipt["budget_resource_name"] = report["budget_resource_name"]
    receipt["polled_at"] = report["latest_poll_at"]
    receipt["actual_cost_krw"] = report["latest_actual_cost_krw"]
    receipt["forecast_cost_krw"] = report["latest_forecast_cost_krw"]
    receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    report["billing_report_hash"] = stable_hash(
        {key: value for key, value in report.items() if key != "billing_report_hash"}
    )
