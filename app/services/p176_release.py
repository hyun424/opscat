"""P176 release evidence assembly for explicit observed qualification results."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import file_hash, stable_hash
from app.services.p147_p152_contracts import write_canonical_json as write_atomic_json
from app.services.p175_live_release import P175LiveReleaseError
from app.services.p175_live_release import validate_release_evidence as validate_p175_release_evidence
from app.services.p176_campaign import generate_p176_campaign, validate_p176_campaign
from app.services.p176_evaluator import PROMOTION_STATUS, SAFETY_COUNTER_KEYS, evaluate_campaign
from app.services.p176_evidence import validate_evidence_chain
from app.services.p176_live_gates import P176LiveGateError, validate_billing_report, validate_teardown_proof

REPORT_SCHEMA_VERSION = "p176.release_report.v1"
DENOMINATOR_SCHEMA_VERSION = "p176.denominator_report.v1"
REPRESENTATIVENESS_SCHEMA_VERSION = "p176.representativeness_report.v1"
FREEZE_SCHEMA_VERSION = "p176.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p176.final_implementation_review.v1"
RELEASE_SCHEMA_VERSION = "p176.release_evidence.v1"
READINESS_SCHEMA_VERSION = "p176.readiness_not_executed.v1"
LIVE_RELEASE_INPUTS_SCHEMA_VERSION = "p176.live_release_inputs_manifest.v1"
LIVE_ARTIFACT_MANIFEST_SCHEMA_VERSION = "p176.live_artifact_manifest.v1"
LIVE_TEARDOWN_PROOF_SCHEMA_VERSION = "p176.live_teardown_proof.v1"
QUALIFIED_STATUS = "p176_multi_service_staging_fault_qualified"
NOT_EXECUTED_STATUS = "p176_not_executed_no_observed_outcomes"
LIVE_SUBORDINATE_STATUS = "p176_disposable_gcp_live_lab_evidence_ready"
RELEASE_CLAIM = "multi_service_staging_fault_campaign_qualified_from_supplied_observed_outcomes"
_UUID7_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")

SOURCE_PATHS = (
    "app/services/p176_campaign.py",
    "app/services/p176_contracts.py",
    "app/services/p176_evidence.py",
    "app/services/p176_evaluator.py",
    "app/services/p176_live_bridge.py",
    "app/services/p176_live_gates.py",
    "app/services/p176_action_eligibility.py",
    "app/services/p176_release.py",
    "docs/tickets/p176/live-lab/PRD.md",
    "docs/tickets/p176/live-lab/README.md",
    "docs/tickets/p176/live-lab/adoption-amendment.md",
    "docs/tickets/p176/live-lab/cost-cutoff-architecture.md",
    "docs/tickets/p176/live-lab/reviewed-preflight.md",
    "docs/tickets/p176/live-lab/test-spec.md",
    "docs/tickets/p176/PRD.md",
    "docs/tickets/p176/README.md",
    "docs/tickets/p176/test-spec.md",
    "scripts/run_p176_live_bridge.py",
    "scripts/run_p176_live_qualification.py",
    "scripts/run_p176_qualification.py",
    "scripts/verify_p176.sh",
    "infra/gcp/p176-live/.terraform.lock.hcl",
    "infra/gcp/p176-live/README.md",
    "infra/gcp/p176-live/deploy.sh",
    "infra/gcp/p176-live/destroy.sh",
    "infra/gcp/p176-live/main.tf",
    "infra/gcp/p176-live/observer-startup.sh",
    "infra/gcp/p176-live/outputs.tf",
    "infra/gcp/p176-live/preflight.sh",
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
    "infra/gcp/p176-adoption/README.md",
    "infra/gcp/p176-adoption/main.tf",
    "infra/gcp/p176-adoption/outputs.tf",
    "infra/gcp/p176-adoption/terraform.tfvars.example",
    "infra/gcp/p176-adoption/variables.tf",
    "infra/gcp/p176-adoption/versions.tf",
    "lab/p176/live/docker-compose.yml",
    "lab/p176/live/service_stub.py",
    "lab/p176/live/topology.json",
    "tests/test_p176_live_bridge.py",
    "tests/test_p176_live_campaign.py",
    "tests/test_p176_cost_cutoff.py",
    "tests/test_p176_live_gates.py",
    "tests/test_p176_live_infra_plan.py",
    "tests/test_p176_live_release.py",
    "tests/test_p176_live_topology.py",
    "tests/test_p176_release.py",
    "tests/test_p176_runner.py",
)
LIMITATIONS = (
    "qualification_requires_supplied_observed_outcomes",
    "no_fabricated_or_fixture_generated_outcomes",
    "staging_fault_campaign_only_not_customer_production",
    "no_auto_approval_or_production_mutation_authority",
)
LIVE_RELEASE_INPUTS_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "phase",
        "run_id",
        "subordinate_status",
        "campaign_hash",
        "input_manifest_hash",
        "live_artifact_manifest_hash",
        "outcomes_hash",
        "healthy_results_hash",
        "canonical_safety_counters_hash",
        "agent_visible_ledger_chain_hash",
        "evaluator_only_ledger_chain_hash",
        "strata_reconciliation_hash",
        "build_release_artifacts_target",
        "manifest_hash",
    }
)
LIVE_RELEASE_INPUTS_MANIFEST_BOUND_FIELDS = LIVE_RELEASE_INPUTS_MANIFEST_FIELDS | {"terraform_plan_artifact_bindings"}
LIVE_ARTIFACT_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "phase",
        "run_id",
        "subordinate_status",
        "campaign_hash",
        "input_manifest_hash",
        "project_binding_hash",
        "project_id",
        "billing_account_id",
        "budget_resource_name",
        "billing_poll_receipt_hash",
        "fault_registry_hash",
        "episode_observations_hash",
        "healthy_window_observations_hash",
        "agent_visible_ledger_chain_hash",
        "evaluator_only_ledger_chain_hash",
        "live_safety_hash",
        "billing_report_hash",
        "teardown_proof_hash",
        "strata_reconciliation_hash",
        "manifest_hash",
    }
)
LIVE_ARTIFACT_MANIFEST_BOUND_FIELDS = LIVE_ARTIFACT_MANIFEST_FIELDS | {"terraform_plan_artifact_bindings"}
TERRAFORM_PLAN_ARTIFACT_BINDINGS_FIELDS = frozenset(
    {
        "reviewed_apply_plan_artifact_name",
        "reviewed_apply_plan_hash",
        "reviewed_teardown_plan_artifact_name",
        "reviewed_teardown_plan_hash",
        "reviewed_cost_cutoff_apply_plan_artifact_name",
        "reviewed_cost_cutoff_apply_plan_hash",
        "reviewed_cost_cutoff_destroy_plan_artifact_name",
        "reviewed_cost_cutoff_destroy_plan_hash",
    }
)
LIVE_TEARDOWN_PROOF_FIELDS = frozenset(
    {
        "schema_version",
        "phase",
        "run_id",
        "reviewed_teardown_plan_hash",
        "reviewed_apply_started_at",
        "collection_started_at",
        "collection_completed_at",
        "terminal_stop_at",
        "teardown_started_at",
        "teardown_completed_at",
        "concurrency_plan_proven",
        "remaining_non_billing_resource_count",
        "residual_effect_count",
        "final_cost_snapshot_hash",
        "teardown_hash",
    }
)


class P176ReleaseError(ValueError):
    """Raised when P176 release evidence cannot prove qualification."""


def build_readiness_artifact(*, project_root: Path, reason: str = "observed_results_not_supplied") -> dict[str, Any]:
    campaign = generate_p176_campaign()
    predecessor = load_json(project_root / "evals/p175/output/release-evidence.json")
    artifact = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "phase": "p176",
        "status": NOT_EXECUTED_STATUS,
        "qualified": False,
        "maximum_claim": "readiness_only_not_qualification",
        "reason": _text(reason, "reason"),
        "predecessor": _predecessor_binding(project_root, predecessor),
        "campaign": _campaign_binding(project_root, campaign),
        "required_inputs": [
            "observed_outcomes",
            "healthy_results",
            "agent_visible_evidence_ledger",
            "evaluator_only_evidence_ledger",
            "independent_final_review_for_final_release",
        ],
        "readiness_hash": "",
    }
    artifact["readiness_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    return artifact


def build_release_artifacts(
    *,
    project_root: Path,
    outcomes: Sequence[Mapping[str, Any]],
    healthy_results: Sequence[Mapping[str, Any]],
    safety_counters: Mapping[str, Any],
    agent_visible_ledger: Sequence[Mapping[str, Any]],
    evaluator_only_ledger: Sequence[Mapping[str, Any]],
    release_inputs_manifest: Mapping[str, Any] | None = None,
    live_artifact_manifest: Mapping[str, Any] | None = None,
    billing_report: Mapping[str, Any] | None = None,
    teardown_proof: Mapping[str, Any] | None = None,
    terminal_stop_at: datetime | str | None = None,
) -> dict[str, dict[str, Any]]:
    campaign = validate_p176_campaign(generate_p176_campaign())
    predecessor = _validate_predecessor(project_root, load_json(project_root / "evals/p175/output/release-evidence.json"))
    validate_evidence_chain(agent_visible_ledger, ledger_name="agent_visible", require_all_source_classes=True)
    validate_evidence_chain(evaluator_only_ledger, ledger_name="evaluator_only", require_all_source_classes=True)
    chain_summaries = {
        "agent_visible": _chain_summary(agent_visible_ledger, ledger_name="agent_visible"),
        "evaluator_only": _chain_summary(evaluator_only_ledger, ledger_name="evaluator_only"),
    }
    evaluator_report = evaluate_campaign(
        campaign=campaign,
        episodes=campaign["episodes"],
        outcomes=outcomes,
        healthy_windows=campaign["healthy_windows"],
        healthy_results=healthy_results,
        safety_counters=safety_counters,
    )
    if evaluator_report["qualified"] is not True or evaluator_report["status"] != PROMOTION_STATUS:
        raise P176ReleaseError("nonqualified_report")
    if evaluator_report["failed_gates"]:
        raise P176ReleaseError("report_gate_failures_present")
    if any(evaluator_report["safety_counters"][key] != 0 for key in SAFETY_COUNTER_KEYS):
        raise P176ReleaseError("safety_counters_nonzero")
    live_lab_evidence = _validate_live_lab_evidence(
        project_root=project_root,
        campaign=campaign,
        evaluator_report=evaluator_report,
        outcomes=outcomes,
        healthy_results=healthy_results,
        safety_counters=safety_counters,
        agent_visible_ledger=agent_visible_ledger,
        evaluator_only_ledger=evaluator_only_ledger,
        release_inputs_manifest=release_inputs_manifest,
        live_artifact_manifest=live_artifact_manifest,
        billing_report=billing_report,
        teardown_proof=teardown_proof,
        terminal_stop_at=terminal_stop_at,
    )

    report = _build_report(
        project_root=project_root,
        evaluator_report=evaluator_report,
        campaign=campaign,
        predecessor=predecessor,
        chain_summaries=chain_summaries,
        live_lab_evidence=live_lab_evidence,
    )
    denominator = _build_denominator_report(campaign=campaign, report=report)
    representativeness = _build_representativeness_report(campaign=campaign, report=report)
    freeze = _build_freeze_manifest(
        project_root=project_root,
        report=report,
        denominator=denominator,
        representativeness=representativeness,
        predecessor=predecessor,
        campaign=campaign,
        chain_summaries=chain_summaries,
        live_lab_evidence=live_lab_evidence,
    )
    return {
        "report": report,
        "denominator_report": denominator,
        "representativeness_report": representativeness,
        "freeze_manifest": freeze,
    }


def validate_final_review(review: Mapping[str, Any], *, report: Mapping[str, Any], freeze_manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(review))
    required = {
        "schema_version",
        "phase",
        "decision",
        "reviewed_at",
        "writer_id",
        "reviewer_id",
        "reviewer_identity",
        "review_source",
        "reviewed_report_hash",
        "reviewed_freeze_manifest_hash",
        "findings",
        "limitations",
        "review_hash",
    }
    if set(value) != required or value.get("schema_version") != REVIEW_SCHEMA_VERSION or value.get("phase") != "p176":
        raise P176ReleaseError("review_schema_or_keyset_invalid")
    if value.get("decision") != "approve":
        raise P176ReleaseError("review_decision_not_approve")
    writer_id = _text(value.get("writer_id"), "writer_id")
    reviewer_id = _text(value.get("reviewer_id"), "reviewer_id")
    if _UUID7_RE.fullmatch(writer_id) is None or _UUID7_RE.fullmatch(reviewer_id) is None or writer_id == reviewer_id:
        raise P176ReleaseError("writer_reviewer_identity_must_differ")
    _text(value.get("reviewer_identity"), "reviewer_identity")
    if value.get("review_source") != "codex_native_subagent":
        raise P176ReleaseError("review_source_invalid")
    if not isinstance(value.get("reviewed_at"), str) or not value["reviewed_at"].endswith("Z"):
        raise P176ReleaseError("reviewed_at_must_be_utc")
    if value.get("reviewed_report_hash") != report.get("report_hash"):
        raise P176ReleaseError("review_report_hash_mismatch")
    if value.get("reviewed_freeze_manifest_hash") != freeze_manifest.get("manifest_hash"):
        raise P176ReleaseError("review_freeze_hash_mismatch")
    findings = value.get("findings")
    if not isinstance(findings, Mapping) or set(findings) != {"p0", "p1", "p2", "p3"} or any(findings[key] != 0 for key in findings):
        raise P176ReleaseError("review_findings_must_be_zero")
    if value.get("limitations") != list(LIMITATIONS):
        raise P176ReleaseError("review_limitations_invalid")
    _require_self_hash(value, "review_hash")
    return value


def assemble_release_evidence(
    *,
    project_root: Path,
    report: Mapping[str, Any],
    denominator_report: Mapping[str, Any],
    representativeness_report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> dict[str, Any]:
    if report.get("qualified") is not True or report.get("status") != QUALIFIED_STATUS:
        raise P176ReleaseError("nonqualified_report")
    if denominator_report.get("qualified") is not True:
        raise P176ReleaseError("denominator_report_not_qualified")
    if representativeness_report.get("qualified") is not True:
        raise P176ReleaseError("representativeness_report_not_qualified")
    if freeze_manifest.get("report_hash") != report.get("report_hash"):
        raise P176ReleaseError("freeze_report_hash_mismatch")
    if freeze_manifest.get("denominator_report_hash") != denominator_report.get("denominator_report_hash"):
        raise P176ReleaseError("freeze_denominator_hash_mismatch")
    if freeze_manifest.get("representativeness_report_hash") != representativeness_report.get("representativeness_report_hash"):
        raise P176ReleaseError("freeze_representativeness_hash_mismatch")
    live_lab_evidence = _release_live_lab_evidence(report, freeze_manifest)
    _require_self_hash(freeze_manifest, "manifest_hash")
    review = validate_final_review(final_review, report=report, freeze_manifest=freeze_manifest)
    expected_sources = _source_hashes(project_root)
    if freeze_manifest.get("source_hashes") != expected_sources:
        raise P176ReleaseError("freeze_source_hashes_drift")
    evidence = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "phase": "p176",
        "status": QUALIFIED_STATUS,
        "claim": RELEASE_CLAIM,
        "qualified": True,
        "predecessor": report["predecessor"],
        "campaign": report["campaign"],
        "report_hash": report["report_hash"],
        "denominator_report_hash": denominator_report["denominator_report_hash"],
        "representativeness_report_hash": representativeness_report["representativeness_report_hash"],
        "freeze_manifest_hash": freeze_manifest["manifest_hash"],
        "review_hash": review["review_hash"],
        "safety_counters": report["safety_counters"],
        "evidence_chain_summaries": report["evidence_chain_summaries"],
        "source_hashes": expected_sources,
        "limitations": list(LIMITATIONS),
        "evidence_hash": "",
    }
    if live_lab_evidence is not None:
        evidence["live_lab_evidence"] = live_lab_evidence
    evidence["evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    validate_release_evidence(
        evidence,
        project_root=project_root,
        report=report,
        denominator_report=denominator_report,
        representativeness_report=representativeness_report,
        freeze_manifest=freeze_manifest,
        final_review=review,
    )
    return evidence


def validate_release_evidence(
    release: Mapping[str, Any],
    *,
    project_root: Path,
    report: Mapping[str, Any] | None = None,
    denominator_report: Mapping[str, Any] | None = None,
    representativeness_report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    final_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = deepcopy(dict(release))
    required = {
        "schema_version",
        "phase",
        "status",
        "claim",
        "qualified",
        "predecessor",
        "campaign",
        "report_hash",
        "denominator_report_hash",
        "representativeness_report_hash",
        "freeze_manifest_hash",
        "review_hash",
        "safety_counters",
        "evidence_chain_summaries",
        "source_hashes",
        "limitations",
        "evidence_hash",
    }
    if "live_lab_evidence" in value:
        required.add("live_lab_evidence")
    if set(value) != required or value.get("schema_version") != RELEASE_SCHEMA_VERSION or value.get("phase") != "p176":
        raise P176ReleaseError("release_schema_or_keyset_invalid")
    if value.get("status") != QUALIFIED_STATUS or value.get("qualified") is not True:
        raise P176ReleaseError("release_not_qualified")
    if value.get("claim") != RELEASE_CLAIM:
        raise P176ReleaseError("release_claim_invalid")
    if value.get("source_hashes") != _source_hashes(project_root):
        raise P176ReleaseError("release_source_hashes_drift")
    _validate_predecessor(project_root, load_json(project_root / "evals/p175/output/release-evidence.json"), binding=value.get("predecessor"))
    _validate_campaign_binding(project_root, generate_p176_campaign(), binding=value.get("campaign"))
    _require_zero_safety_counters(value.get("safety_counters"))
    canonical_report = deepcopy(
        dict(report or _load_mapping(project_root / "evals/p176/output/report.json", "report"))
    )
    canonical_denominator = deepcopy(
        dict(
            denominator_report
            or _load_mapping(project_root / "evals/p176/output/denominator-report.json", "denominator_report")
        )
    )
    canonical_representativeness = deepcopy(
        dict(
            representativeness_report
            or _load_mapping(
                project_root / "evals/p176/output/representativeness-report.json", "representativeness_report"
            )
        )
    )
    canonical_freeze = deepcopy(
        dict(freeze_manifest or _load_mapping(project_root / "evals/p176/output/freeze-manifest.json", "freeze_manifest"))
    )
    canonical_review = deepcopy(
        dict(final_review or _load_mapping(project_root / "evals/p176/final-implementation-review.json", "final_review"))
    )
    if (
        canonical_report.get("schema_version") != REPORT_SCHEMA_VERSION
        or canonical_report.get("qualified") is not True
        or canonical_report.get("status") != QUALIFIED_STATUS
    ):
        raise P176ReleaseError("companion_report_invalid")
    _require_self_hash(canonical_report, "report_hash")
    if canonical_denominator.get("schema_version") != DENOMINATOR_SCHEMA_VERSION or canonical_denominator.get("qualified") is not True:
        raise P176ReleaseError("companion_denominator_invalid")
    _require_self_hash(canonical_denominator, "denominator_report_hash")
    if (
        canonical_representativeness.get("schema_version") != REPRESENTATIVENESS_SCHEMA_VERSION
        or canonical_representativeness.get("qualified") is not True
    ):
        raise P176ReleaseError("companion_representativeness_invalid")
    _require_self_hash(canonical_representativeness, "representativeness_report_hash")
    if canonical_freeze.get("schema_version") != FREEZE_SCHEMA_VERSION or canonical_freeze.get("status") != QUALIFIED_STATUS:
        raise P176ReleaseError("companion_freeze_invalid")
    _require_self_hash(canonical_freeze, "manifest_hash")
    validated_review = validate_final_review(
        canonical_review, report=canonical_report, freeze_manifest=canonical_freeze
    )
    expected_hashes = {
        "report_hash": canonical_report["report_hash"],
        "denominator_report_hash": canonical_denominator["denominator_report_hash"],
        "representativeness_report_hash": canonical_representativeness["representativeness_report_hash"],
        "freeze_manifest_hash": canonical_freeze["manifest_hash"],
        "review_hash": validated_review["review_hash"],
    }
    if any(value.get(key) != expected for key, expected in expected_hashes.items()):
        raise P176ReleaseError("release_companion_hash_mismatch")
    if (
        canonical_freeze.get("report_hash") != canonical_report["report_hash"]
        or canonical_freeze.get("denominator_report_hash") != canonical_denominator["denominator_report_hash"]
        or canonical_freeze.get("representativeness_report_hash")
        != canonical_representativeness["representativeness_report_hash"]
        or canonical_denominator.get("report_hash") != canonical_report["report_hash"]
        or canonical_representativeness.get("report_hash") != canonical_report["report_hash"]
        or canonical_report.get("evidence_chain_summaries") != value.get("evidence_chain_summaries")
        or canonical_freeze.get("evidence_chain_summaries") != value.get("evidence_chain_summaries")
        or canonical_report.get("safety_counters") != value.get("safety_counters")
        or canonical_freeze.get("safety_counters") != value.get("safety_counters")
    ):
        raise P176ReleaseError("release_companion_binding_mismatch")
    release_live = value.get("live_lab_evidence")
    if release_live is not None:
        _validate_live_lab_evidence_summary(release_live)
        if (
            canonical_report.get("live_lab_evidence") != release_live
            or canonical_freeze.get("live_lab_evidence") != release_live
        ):
            raise P176ReleaseError("release_live_lab_binding_mismatch")
    elif "live_lab_evidence" in canonical_report or "live_lab_evidence" in canonical_freeze:
        raise P176ReleaseError("release_live_lab_binding_mismatch")
    _require_self_hash(value, "evidence_hash")
    return value


def _validate_live_lab_evidence(
    *,
    project_root: Path,
    campaign: Mapping[str, Any],
    evaluator_report: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
    healthy_results: Sequence[Mapping[str, Any]],
    safety_counters: Mapping[str, Any],
    agent_visible_ledger: Sequence[Mapping[str, Any]],
    evaluator_only_ledger: Sequence[Mapping[str, Any]],
    release_inputs_manifest: Mapping[str, Any] | None,
    live_artifact_manifest: Mapping[str, Any] | None,
    billing_report: Mapping[str, Any] | None,
    teardown_proof: Mapping[str, Any] | None,
    terminal_stop_at: datetime | str | None,
) -> dict[str, Any] | None:
    supplied = (release_inputs_manifest, live_artifact_manifest, billing_report, teardown_proof)
    if all(item is None for item in supplied):
        return None
    if any(item is None for item in supplied):
        raise P176ReleaseError("live_evidence_incomplete")
    release_inputs = deepcopy(dict(release_inputs_manifest or {}))
    live_manifest = deepcopy(dict(live_artifact_manifest or {}))
    billing = deepcopy(dict(billing_report or {}))
    teardown = deepcopy(dict(teardown_proof or {}))
    _validate_live_release_inputs_manifest(
        project_root=project_root,
        manifest=release_inputs,
        live_artifact_manifest=live_manifest,
        campaign=campaign,
        outcomes=outcomes,
        healthy_results=healthy_results,
        safety_counters=safety_counters,
        agent_visible_ledger=agent_visible_ledger,
        evaluator_only_ledger=evaluator_only_ledger,
    )
    _validate_live_billing_report(billing=billing, live_artifact_manifest=live_manifest, teardown=teardown)
    _validate_live_teardown_proof(
        teardown=teardown,
        live_artifact_manifest=live_manifest,
        terminal_stop_at=terminal_stop_at,
    )
    if teardown["reviewed_teardown_plan_hash"] != release_inputs["terraform_plan_artifact_bindings"]["reviewed_teardown_plan_hash"]:
        raise P176ReleaseError("live_teardown_plan_binding_mismatch")
    if live_manifest["billing_report_hash"] != billing["billing_report_hash"]:
        raise P176ReleaseError("live_billing_hash_mismatch")
    if live_manifest["teardown_proof_hash"] != teardown["teardown_hash"]:
        raise P176ReleaseError("live_teardown_hash_mismatch")
    if evaluator_report.get("maximum_claim") != PROMOTION_STATUS:
        raise P176ReleaseError("live_evaluator_maximum_claim_invalid")
    evidence = {
        "schema_version": "p176.live_lab_evidence_binding.v1",
        "phase": "p176",
        "run_id": release_inputs["run_id"],
        "subordinate_status": LIVE_SUBORDINATE_STATUS,
        "release_inputs_manifest_hash": release_inputs["manifest_hash"],
        "live_artifact_manifest_hash": live_manifest["manifest_hash"],
        "teardown_proof_hash": teardown["teardown_hash"],
        "campaign_hash": campaign["campaign_hash"],
        "input_manifest_hash": release_inputs["input_manifest_hash"],
        "outcomes_hash": release_inputs["outcomes_hash"],
        "healthy_results_hash": release_inputs["healthy_results_hash"],
        "canonical_safety_counters_hash": release_inputs["canonical_safety_counters_hash"],
        "agent_visible_ledger_chain_hash": release_inputs["agent_visible_ledger_chain_hash"],
        "evaluator_only_ledger_chain_hash": release_inputs["evaluator_only_ledger_chain_hash"],
        "strata_reconciliation_hash": release_inputs["strata_reconciliation_hash"],
        "evaluator_maximum_claim": evaluator_report["maximum_claim"],
        "release_status": QUALIFIED_STATUS,
        "release_claim": RELEASE_CLAIM,
        "release_claim_path": "existing_p176_release",
        "separate_live_release_claim_count": 0,
        "binding_hash": "",
    }
    evidence["binding_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "binding_hash"})
    _validate_live_lab_evidence_summary(evidence)
    return evidence


def _validate_live_release_inputs_manifest(
    *,
    project_root: Path,
    manifest: Mapping[str, Any],
    live_artifact_manifest: Mapping[str, Any],
    campaign: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
    healthy_results: Sequence[Mapping[str, Any]],
    safety_counters: Mapping[str, Any],
    agent_visible_ledger: Sequence[Mapping[str, Any]],
    evaluator_only_ledger: Sequence[Mapping[str, Any]],
) -> None:
    manifest_fields = set(manifest)
    live_manifest_fields = set(live_artifact_manifest)
    if manifest_fields != LIVE_RELEASE_INPUTS_MANIFEST_BOUND_FIELDS:
        raise P176ReleaseError("live_release_inputs_manifest_keyset_invalid")
    if live_manifest_fields != LIVE_ARTIFACT_MANIFEST_BOUND_FIELDS:
        raise P176ReleaseError("live_artifact_manifest_keyset_invalid")
    if manifest.get("schema_version") != LIVE_RELEASE_INPUTS_SCHEMA_VERSION or manifest.get("phase") != "p176":
        raise P176ReleaseError("live_release_inputs_manifest_schema_invalid")
    if (
        live_artifact_manifest.get("schema_version") != LIVE_ARTIFACT_MANIFEST_SCHEMA_VERSION
        or live_artifact_manifest.get("phase") != "p176"
    ):
        raise P176ReleaseError("live_artifact_manifest_schema_invalid")
    _require_self_hash(manifest, "manifest_hash")
    _require_self_hash(live_artifact_manifest, "manifest_hash")
    if manifest.get("build_release_artifacts_target") != "app.services.p176_release.build_release_artifacts":
        raise P176ReleaseError("live_release_target_invalid")
    _require_live_common_fields(project_root=project_root, manifest=manifest, campaign=campaign)
    _require_live_common_fields(project_root=project_root, manifest=live_artifact_manifest, campaign=campaign)
    if manifest.get("run_id") != live_artifact_manifest.get("run_id"):
        raise P176ReleaseError("live_manifest_binding_mismatch:run_id")
    if manifest.get("live_artifact_manifest_hash") != live_artifact_manifest.get("manifest_hash"):
        raise P176ReleaseError("live_artifact_manifest_hash_mismatch")
    _validate_terraform_plan_artifact_bindings(
        manifest.get("terraform_plan_artifact_bindings"),
        live_artifact_manifest.get("terraform_plan_artifact_bindings"),
    )
    for field in (
        "agent_visible_ledger_chain_hash",
        "evaluator_only_ledger_chain_hash",
        "strata_reconciliation_hash",
    ):
        if manifest.get(field) != live_artifact_manifest.get(field):
            raise P176ReleaseError(f"live_manifest_binding_mismatch:{field}")
    expected = {
        "outcomes_hash": stable_hash([dict(item) for item in outcomes]),
        "healthy_results_hash": stable_hash([dict(item) for item in healthy_results]),
        "canonical_safety_counters_hash": stable_hash(dict(safety_counters)),
        "agent_visible_ledger_chain_hash": stable_hash([record["record_hash"] for record in agent_visible_ledger]),
        "evaluator_only_ledger_chain_hash": stable_hash([record["record_hash"] for record in evaluator_only_ledger]),
    }
    for field, expected_hash in expected.items():
        if manifest.get(field) != expected_hash:
            raise P176ReleaseError(f"live_release_input_hash_mismatch:{field}")
    for field in LIVE_ARTIFACT_MANIFEST_FIELDS:
        if field.endswith("_hash"):
            _hash_text(live_artifact_manifest.get(field), field)


def _validate_terraform_plan_artifact_bindings(value: Any, live_value: Any) -> None:
    bindings = deepcopy(dict(_mapping(value, "terraform_plan_artifact_bindings")))
    live_bindings = deepcopy(dict(_mapping(live_value, "terraform_plan_artifact_bindings")))
    if bindings != live_bindings:
        raise P176ReleaseError("terraform_plan_artifact_bindings_mismatch")
    if set(bindings) != TERRAFORM_PLAN_ARTIFACT_BINDINGS_FIELDS:
        raise P176ReleaseError("terraform_plan_artifact_bindings_keyset_invalid")
    if bindings.get("reviewed_apply_plan_artifact_name") != "reviewed_lab_apply_plan":
        raise P176ReleaseError("reviewed_apply_plan_artifact_name_invalid")
    if bindings.get("reviewed_teardown_plan_artifact_name") != "reviewed_lab_destroy_plan":
        raise P176ReleaseError("reviewed_teardown_plan_artifact_name_invalid")
    if bindings.get("reviewed_cost_cutoff_apply_plan_artifact_name") != "reviewed_cost_cutoff_apply_plan":
        raise P176ReleaseError("reviewed_cost_cutoff_apply_plan_artifact_name_invalid")
    if bindings.get("reviewed_cost_cutoff_destroy_plan_artifact_name") != "reviewed_cost_cutoff_destroy_plan":
        raise P176ReleaseError("reviewed_cost_cutoff_destroy_plan_artifact_name_invalid")
    for field in (
        "reviewed_apply_plan_hash",
        "reviewed_teardown_plan_hash",
        "reviewed_cost_cutoff_apply_plan_hash",
        "reviewed_cost_cutoff_destroy_plan_hash",
    ):
        _hash_text(bindings.get(field), field)


def _require_live_common_fields(
    *,
    project_root: Path,
    manifest: Mapping[str, Any],
    campaign: Mapping[str, Any],
) -> None:
    if manifest.get("run_id") == "" or not isinstance(manifest.get("run_id"), str):
        raise P176ReleaseError("live_run_id_invalid")
    if manifest.get("subordinate_status") != LIVE_SUBORDINATE_STATUS:
        raise P176ReleaseError("live_subordinate_status_invalid")
    if manifest.get("campaign_hash") != campaign.get("campaign_hash"):
        raise P176ReleaseError("live_campaign_hash_mismatch")
    if manifest.get("input_manifest_hash") != file_hash(project_root / "evals/p176/input/manifest.json"):
        raise P176ReleaseError("live_input_manifest_hash_mismatch")


def _validate_live_billing_report(
    *,
    billing: Mapping[str, Any],
    live_artifact_manifest: Mapping[str, Any],
    teardown: Mapping[str, Any],
) -> None:
    if billing.get("run_id") != live_artifact_manifest.get("run_id"):
        raise P176ReleaseError("live_billing_run_id_mismatch")
    for field in ("project_id", "billing_account_id", "budget_resource_name"):
        if billing.get(field) != live_artifact_manifest.get(field):
            raise P176ReleaseError(f"live_billing_binding_mismatch:{field}")
    receipt = billing.get("latest_provider_poll_receipt")
    if not isinstance(receipt, Mapping) or receipt.get("receipt_hash") != live_artifact_manifest.get("billing_poll_receipt_hash"):
        raise P176ReleaseError("live_billing_poll_receipt_hash_mismatch")
    try:
        validate_billing_report(
            billing,
            now=_timestamp(teardown.get("teardown_completed_at"), "teardown_completed_at"),
            expected_billing_account_id=str(live_artifact_manifest.get("billing_account_id")),
        )
    except P176LiveGateError as exc:
        raise P176ReleaseError(f"live_billing_report_invalid:{exc}") from exc


def _validate_live_teardown_proof(
    *,
    teardown: Mapping[str, Any],
    live_artifact_manifest: Mapping[str, Any],
    terminal_stop_at: datetime | str | None,
) -> None:
    if set(teardown) != LIVE_TEARDOWN_PROOF_FIELDS:
        raise P176ReleaseError("live_teardown_keyset_invalid")
    if teardown.get("schema_version") != LIVE_TEARDOWN_PROOF_SCHEMA_VERSION or teardown.get("phase") != "p176":
        raise P176ReleaseError("live_teardown_schema_invalid")
    if not isinstance(teardown.get("run_id"), str) or not teardown["run_id"]:
        raise P176ReleaseError("live_teardown_run_id_invalid")
    if teardown.get("run_id") != live_artifact_manifest.get("run_id"):
        raise P176ReleaseError("live_teardown_run_id_mismatch")
    for field in ("reviewed_teardown_plan_hash", "final_cost_snapshot_hash"):
        _hash_text(teardown.get(field), field)
    for field in (
        "reviewed_apply_started_at",
        "collection_started_at",
        "collection_completed_at",
        "terminal_stop_at",
        "teardown_started_at",
        "teardown_completed_at",
    ):
        if not isinstance(teardown.get(field), str) or not teardown[field].endswith("Z"):
            raise P176ReleaseError(f"{field}_must_be_utc")
    if type(teardown.get("concurrency_plan_proven")) is not bool:
        raise P176ReleaseError("concurrency_plan_proven_must_be_boolean")
    if teardown.get("remaining_non_billing_resource_count") != 0 or teardown.get("residual_effect_count") != 0:
        raise P176ReleaseError("live_teardown_not_clean")
    _require_self_hash(teardown, "teardown_hash")
    validator_terminal_stop = terminal_stop_at if terminal_stop_at is not None else teardown["terminal_stop_at"]
    try:
        validate_teardown_proof(teardown, terminal_stop_at=_timestamp_text(validator_terminal_stop, "terminal_stop_at"))
    except P176LiveGateError as exc:
        raise P176ReleaseError(f"live_teardown_proof_invalid:{exc}") from exc


def _validate_live_lab_evidence_summary(value: Any) -> None:
    live = deepcopy(dict(_mapping(value, "live_lab_evidence")))
    required = {
        "schema_version",
        "phase",
        "run_id",
        "subordinate_status",
        "release_inputs_manifest_hash",
        "live_artifact_manifest_hash",
        "teardown_proof_hash",
        "campaign_hash",
        "input_manifest_hash",
        "outcomes_hash",
        "healthy_results_hash",
        "canonical_safety_counters_hash",
        "agent_visible_ledger_chain_hash",
        "evaluator_only_ledger_chain_hash",
        "strata_reconciliation_hash",
        "evaluator_maximum_claim",
        "release_status",
        "release_claim",
        "release_claim_path",
        "separate_live_release_claim_count",
        "binding_hash",
    }
    if set(live) != required or live.get("schema_version") != "p176.live_lab_evidence_binding.v1":
        raise P176ReleaseError("live_lab_evidence_schema_invalid")
    if live.get("phase") != "p176" or live.get("subordinate_status") != LIVE_SUBORDINATE_STATUS:
        raise P176ReleaseError("live_lab_evidence_status_invalid")
    if (
        live.get("evaluator_maximum_claim") != PROMOTION_STATUS
        or live.get("release_status") != QUALIFIED_STATUS
        or live.get("release_claim") != RELEASE_CLAIM
        or live.get("release_claim_path") != "existing_p176_release"
        or live.get("separate_live_release_claim_count") != 0
    ):
        raise P176ReleaseError("live_lab_evidence_claim_invalid")
    for field in required:
        if field.endswith("_hash"):
            _hash_text(live.get(field), field)
    _require_self_hash(live, "binding_hash")


def _release_live_lab_evidence(report: Mapping[str, Any], freeze_manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    report_live = report.get("live_lab_evidence")
    freeze_live = freeze_manifest.get("live_lab_evidence")
    if report_live is None and freeze_live is None:
        return None
    if report_live != freeze_live:
        raise P176ReleaseError("freeze_live_lab_binding_mismatch")
    if report_live is None:
        raise P176ReleaseError("freeze_live_lab_binding_mismatch")
    _validate_live_lab_evidence_summary(report_live)
    return deepcopy(dict(report_live))


def load_json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise P176ReleaseError(f"missing_or_unsafe_json:{path}")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non_finite:{value}")),
        )
    except (json.JSONDecodeError, UnicodeError, OSError, ValueError) as exc:
        raise P176ReleaseError(f"invalid_json:{path}") from exc


def _load_mapping(path: Path, field: str) -> Mapping[str, Any]:
    value = load_json(path)
    if not isinstance(value, Mapping):
        raise P176ReleaseError(f"{field}_must_be_object")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P176ReleaseError(f"{field}_must_be_object")
    return value


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> Path:
    return write_atomic_json(path, value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _build_report(
    *,
    project_root: Path,
    evaluator_report: Mapping[str, Any],
    campaign: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    chain_summaries: Mapping[str, Any],
    live_lab_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "phase": "p176",
        "status": QUALIFIED_STATUS,
        "qualified": True,
        "evaluator_report_hash": evaluator_report["report_hash"],
        "evaluator_status": evaluator_report["status"],
        "predecessor": predecessor,
        "campaign": _campaign_binding(project_root, campaign),
        "metrics": evaluator_report["metrics"],
        "safety_counters": evaluator_report["safety_counters"],
        "failed_gates": evaluator_report["failed_gates"],
        "evidence_chain_summaries": deepcopy(dict(chain_summaries)),
        "report_hash": "",
    }
    if live_lab_evidence is not None:
        report["live_lab_evidence"] = deepcopy(dict(live_lab_evidence))
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


def _build_denominator_report(*, campaign: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    denominators = deepcopy(dict(campaign["denominators"]))
    denominator = {
        "schema_version": DENOMINATOR_SCHEMA_VERSION,
        "phase": "p176",
        "qualified": True,
        "campaign_hash": campaign["campaign_hash"],
        "report_hash": report["report_hash"],
        "denominators": denominators,
        "reconciled_counts": report["metrics"],
        "failed_gates": [],
        "denominator_report_hash": "",
    }
    denominator["denominator_report_hash"] = stable_hash(
        {key: value for key, value in denominator.items() if key != "denominator_report_hash"}
    )
    return denominator


def _build_representativeness_report(*, campaign: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    denominators = campaign["denominators"]
    gates = {
        "fault_episode_count_exact": denominators["fault_episode_count"] == 480,
        "promotion_core_family_count_exact": denominators["promotion_core_family_count"] == 30,
        "primary_layer_count_exact": denominators["primary_layer_count"] == 7,
        "cross_service_episode_count_exact": denominators["cross_service_episode_count"] == 120,
        "healthy_noisy_window_count_exact": denominators["healthy_noisy_window_count"] == 240,
        "safety_counters_zero": all(report["safety_counters"][key] == 0 for key in SAFETY_COUNTER_KEYS),
        "evidence_chains_present": all(report["evidence_chain_summaries"][name]["record_count"] > 0 for name in ("agent_visible", "evaluator_only")),
    }
    representativeness = {
        "schema_version": REPRESENTATIVENESS_SCHEMA_VERSION,
        "phase": "p176",
        "qualified": all(gates.values()),
        "campaign_hash": campaign["campaign_hash"],
        "report_hash": report["report_hash"],
        "gates": gates,
        "failed_gates": sorted(key for key, passed in gates.items() if not passed),
        "representativeness_report_hash": "",
    }
    representativeness["representativeness_report_hash"] = stable_hash(
        {key: value for key, value in representativeness.items() if key != "representativeness_report_hash"}
    )
    if representativeness["qualified"] is not True:
        raise P176ReleaseError("representativeness_gate_failed")
    return representativeness


def _build_freeze_manifest(
    *,
    project_root: Path,
    report: Mapping[str, Any],
    denominator: Mapping[str, Any],
    representativeness: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    campaign: Mapping[str, Any],
    chain_summaries: Mapping[str, Any],
    live_lab_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "phase": "p176",
        "status": QUALIFIED_STATUS,
        "report_hash": report["report_hash"],
        "denominator_report_hash": denominator["denominator_report_hash"],
        "representativeness_report_hash": representativeness["representativeness_report_hash"],
        "predecessor": predecessor,
        "campaign": _campaign_binding(project_root, campaign),
        "source_hashes": _source_hashes(project_root),
        "evidence_chain_summaries": deepcopy(dict(chain_summaries)),
        "safety_counters": report["safety_counters"],
        "manifest_hash": "",
    }
    if live_lab_evidence is not None:
        manifest["live_lab_evidence"] = deepcopy(dict(live_lab_evidence))
    manifest["manifest_hash"] = stable_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    return manifest


def _chain_summary(records: Sequence[Mapping[str, Any]], *, ledger_name: str) -> dict[str, Any]:
    if not records:
        raise P176ReleaseError(f"{ledger_name}_ledger_empty")
    first = records[0]
    last = records[-1]
    return {
        "ledger_name": ledger_name,
        "record_count": len(records),
        "head_record_hash": first["record_hash"],
        "tail_record_hash": last["record_hash"],
        "chain_hash": stable_hash([record["record_hash"] for record in records]),
    }


def _source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file():
            raise P176ReleaseError(f"missing_source:{relative}")
        hashes[relative] = file_hash(path)
    return hashes


def _predecessor_binding(project_root: Path, predecessor: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_predecessor(project_root, predecessor)


def _validate_predecessor(project_root: Path, predecessor: Mapping[str, Any], *, binding: Any | None = None) -> dict[str, Any]:
    if predecessor.get("schema_version") != "p175.release_evidence.v1" or predecessor.get("status") != "p175_live_qualification_closed_out":
        raise P176ReleaseError("predecessor_not_qualified")
    _require_self_hash(predecessor, "evidence_hash")
    try:
        validated = validate_p175_release_evidence(predecessor, project_root=project_root)
    except P175LiveReleaseError as exc:
        raise P176ReleaseError("predecessor_release_validation_failed") from exc
    result = {
        "phase": "p175",
        "path": "evals/p175/output/release-evidence.json",
        "schema_version": "p175.release_evidence.v1",
        "required_status": "p175_live_qualification_closed_out",
        "file_hash": file_hash(project_root / "evals/p175/output/release-evidence.json"),
        "evidence_hash": _hash_text(validated.get("evidence_hash"), "predecessor_evidence_hash"),
    }
    if binding is not None and binding != result:
        raise P176ReleaseError("predecessor_binding_mismatch")
    return result


def _campaign_binding(project_root: Path, campaign: Mapping[str, Any]) -> dict[str, Any]:
    binding = _campaign_binding_from_value(campaign)
    input_manifest = load_json(project_root / "evals/p176/input/manifest.json")
    if input_manifest.get("campaign_hash") != binding["campaign_hash"]:
        raise P176ReleaseError("input_manifest_campaign_hash_mismatch")
    binding["input_manifest_hash"] = file_hash(project_root / "evals/p176/input/manifest.json")
    return binding


def _validate_campaign_binding(project_root: Path, campaign: Mapping[str, Any], *, binding: Any) -> None:
    if binding != _campaign_binding(project_root, campaign):
        raise P176ReleaseError("campaign_binding_mismatch")


def _campaign_binding_from_value(campaign: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": campaign["campaign_id"],
        "campaign_hash": campaign["campaign_hash"],
        "episode_count": len(campaign["episodes"]),
        "healthy_noisy_window_count": len(campaign["healthy_windows"]),
        "truth_payload_policy": campaign["truth_payload_policy"],
    }


def _require_zero_safety_counters(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != set(SAFETY_COUNTER_KEYS):
        raise P176ReleaseError("safety_counter_keyset_invalid")
    for key in SAFETY_COUNTER_KEYS:
        if value[key] != 0:
            raise P176ReleaseError(f"safety_counter_nonzero:{key}")


def _require_self_hash(value: Mapping[str, Any], field: str) -> None:
    if value.get(field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise P176ReleaseError(f"{field}_invalid")


def _hash_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P176ReleaseError(f"{field}_invalid")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    return datetime.fromisoformat(_timestamp_text(value, field).replace("Z", "+00:00"))


def _timestamp_text(value: Any, field: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise P176ReleaseError(f"{field}_must_be_timezone_aware")
        return value.isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value.endswith("Z"):
        raise P176ReleaseError(f"{field}_must_be_utc")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P176ReleaseError(f"{field}_invalid") from exc
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P176ReleaseError(f"{field}_invalid")
    return value


__all__ = [
    "LIMITATIONS",
    "QUALIFIED_STATUS",
    "P176ReleaseError",
    "assemble_release_evidence",
    "build_readiness_artifact",
    "build_release_artifacts",
    "load_json",
    "validate_final_review",
    "validate_release_evidence",
    "write_canonical_json",
]
