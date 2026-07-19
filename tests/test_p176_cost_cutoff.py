from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = ROOT / "infra" / "gcp" / "p176-cost-cutoff"
LIVE = ROOT / "infra" / "gcp" / "p176-live"
DOC = ROOT / "docs" / "tickets" / "p176" / "live-lab" / "cost-cutoff-architecture.md"
P176_EVIDENCE = ROOT / "evals" / "p176"

ADMIN_PROJECT = "opscat-p176-admin-" + "test01"
LAB_PROJECT = "opscat-p176-live-" + "test01"
ORG_ID = "000000000000"
BILLING_ACCOUNT = "-".join(("ABCDEF", "123456", "789ABC"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _terraform(directory: Path = CUTOFF) -> str:
    return "\n".join(_read(path) for path in sorted(directory.glob("*.tf")))


def test_cost_cutoff_module_declares_out_of_band_control_plane() -> None:
    required = {
        "versions.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "terraform.tfvars.template",
        "preflight.sh",
        "deploy.sh",
        "destroy.sh",
        "verify-apply-plan.jq",
        "verify-destroy-plan.jq",
        "README.md",
    }
    assert required <= {path.name for path in CUTOFF.iterdir() if path.is_file()}

    terraform = _terraform()
    assert 'resource "google_project" "admin"' in terraform
    assert 'resource "google_project" "lab"' in terraform
    assert "org_id              = var.org_id" in terraform
    assert "billing_account     = var.billing_account_id" in terraform
    assert terraform.count("auto_create_network = false") == 2
    assert terraform.count('deletion_policy     = "DELETE"') == 2
    assert "project = var.admin_project_id" not in _read(CUTOFF / "versions.tf")
    assert 'can(regex("^opscat-p176-admin-[a-z0-9-]{6,20}$", var.admin_project_id))' in terraform
    assert 'can(regex("^opscat-p176-live-[a-z0-9-]{6,20}$", var.lab_project_id))' in terraform
    assert "var.admin_project_id != var.lab_project_id" in terraform
    assert "non-lab admin project" in terraform
    assert "lab-hosted controller" in terraform
    assert "shared-vpc" in terraform
    assert "production" in terraform
    assert "roles/owner" not in terraform
    assert "roles/editor" not in terraform
    assert "google_service_account_key" not in terraform
    assert "roles/iam.serviceAccountTokenCreator" not in terraform
    assert "roles/iam.serviceAccountUser" not in terraform
    assert "google_project_iam_binding" not in terraform
    assert "google_organization_iam" not in terraform
    assert "google_folder_iam" not in terraform
    assert "google_compute_shared_vpc" not in terraform


def test_cost_cutoff_resources_cover_budget_eventarc_workflow_scheduler_and_receipts() -> None:
    terraform = _terraform()
    for service in (
        "billingbudgets.googleapis.com",
        "cloudbilling.googleapis.com",
        "cloudscheduler.googleapis.com",
        "compute.googleapis.com",
        "eventarc.googleapis.com",
        "iam.googleapis.com",
        "logging.googleapis.com",
        "pubsub.googleapis.com",
        "serviceusage.googleapis.com",
        "storage.googleapis.com",
        "workflows.googleapis.com",
        "iap.googleapis.com",
        "monitoring.googleapis.com",
        "oslogin.googleapis.com",
    ):
        assert service in terraform
    assert "cloudresourcemanager.googleapis.com" not in terraform
    assert 'resource "google_pubsub_topic" "budget_notifications"' in terraform
    assert 'name    = "p176-cost-cutoff-budget"' in terraform
    assert 'budget_notification_publisher_member = "serviceAccount:${join("@", ["billing-budget-notifications", "system.gserviceaccount.com"])}"' in terraform
    assert 'role    = "roles/pubsub.publisher"' in terraform
    assert 'resource "google_eventarc_trigger" "budget_to_workflow"' in terraform
    assert 'value     = "google.cloud.pubsub.topic.v1.messagePublished"' in terraform
    assert 'workflow = google_workflows_workflow.cutoff.name' in terraform
    assert 'resource "google_workflows_workflow" "cutoff"' in terraform
    assert 'resource "google_cloud_scheduler_job" "fallback_probe"' in terraform
    assert "*/5 * * * *" in terraform
    assert 'resource "google_storage_bucket" "receipts"' in terraform
    assert "uniform_bucket_level_access = true" in terraform
    assert 'public_access_prevention    = "enforced"' in terraform
    assert "versioning" in terraform
    assert "retention_policy" in terraform
    assert "is_locked        = true" in terraform
    assert "age        = 2" in terraform
    assert "p176-cost-cutoff-workflow" in terraform
    assert "p176-cost-cutoff-eventarc" in terraform
    assert "p176-cost-cutoff-scheduler" in terraform
    assert 'resource "google_billing_budget" "lab"' in terraform
    assert 'projects = ["projects/${google_project.lab.number}"]' in terraform
    assert "google_project.lab.number" in terraform
    assert 'pubsub_topic                     = google_pubsub_topic.budget_notifications.id' in terraform
    assert 'resource "google_monitoring_notification_channel" "budget_email"' in terraform


def test_cost_cutoff_workflow_contract_has_thresholds_ordering_and_durable_dedupe() -> None:
    terraform = _terraform()
    assert "var.soft_stop_krw == 24000" in terraform
    assert "var.hard_cutoff_krw == 27000" in terraform
    assert "var.budget_krw == 30000" in terraform
    assert "var.stale_after_seconds == 600" in terraform
    assert "var.terminal_ttl_seconds == 129600" in terraform
    assert "var.absolute_lease_seconds == 172800" in terraform
    assert "ifGenerationMatch: 0" in terraform
    assert "alreadyExists" in terraform
    assert "stop_compute_before_disable_billing" in terraform
    assert "googleapis.compute.v1.instances.stop" in terraform
    assert "googleapis.cloudbilling.v1.projects.updateBillingInfo" in terraform
    assert terraform.index("googleapis.compute.v1.instances.stop") < terraform.index(
        "googleapis.cloudbilling.v1.projects.updateBillingInfo"
    )
    assert "billingAccountName: null" in terraform


def test_cost_cutoff_runtime_uses_durable_state_and_conservative_forecast() -> None:
    terraform = _terraform()
    assert 'costAmount     = "0"' not in terraform
    assert 'costAmount = "0"' not in terraform
    assert 'default(map.get(payload, "costAmount"), "0")' not in terraform
    assert 'triggerKind    = "timer"' in terraform
    assert 'thresholdBasis = "DURABLE_STATE_TIMER"' in terraform
    assert 'state_object: "state/latest.json"' in terraform
    assert "readLatestDurableState" in terraform
    assert "fail_closed_missing_budget_provider_state" in terraform
    assert "fail_closed_stale_budget_provider_state" in terraform
    assert "timer_requires_last_durable_budget_provider_state" in terraform
    assert "now_epoch - time.parse(observed_at) > stale_after_seconds" in terraform
    assert "forecast_amount_krw * 1.15" in terraform
    assert "effective_amount_krw" in terraform
    assert "writeProviderStateReceipt" in terraform
    assert "updateCanonicalLatestStateAtomically" in terraform
    assert "ifGenerationMatch: $${int(existing_latest_state.generation)}" in terraform
    assert "receipt_type: canonical_latest_budget_provider_state" in terraform


def test_cost_cutoff_decodes_real_eventarc_pubsub_budget_messages() -> None:
    envelope = _budget_cloudevent(
        {
            "budgetDisplayName": "p176-live-lab-budget",
            "costAmount": 24500,
            "budgetAmount": 30000,
            "currencyCode": "KRW",
            "forecastAmount": 26000.25,
        }
    )

    assert envelope["type"] == "google.cloud.pubsub.topic.v1.messagePublished"
    assert _decoded_budget_payload(envelope) == {
        "budgetDisplayName": "p176-live-lab-budget",
        "costAmount": 24500,
        "budgetAmount": 30000,
        "currencyCode": "KRW",
        "forecastAmount": 26000.25,
    }

    terraform = _terraform()
    assert "event.data.message.data" in terraform
    assert "json.decode(base64.decode(pubsub_message_data))" in terraform
    assert terraform.index("decodeBudgetPubsubCloudEvent") < terraform.index(
        "writeProviderStateReceipt"
    )
    assert 'map.get(budget_payload, "costAmount")' in terraform
    assert 'map.get(budget_payload, "budgetAmount")' in terraform
    assert 'map.get(budget_payload, "currencyCode")' in terraform
    assert 'map.get(budget_payload, "forecastAmount")' in terraform
    assert "forecast_amount_krw_metadata: \"unavailable\"" in terraform


def test_cost_cutoff_rejects_malformed_budget_events_before_durable_state() -> None:
    malformed_envelopes = [
        {"data": {"message": {}}},
        {
            "data": {
                "message": {
                    "data": base64.b64encode(b"not json").decode("ascii"),
                }
            }
        },
        _budget_cloudevent(
            {"budgetAmount": 30000, "currencyCode": "KRW"},
        ),
        _budget_cloudevent(
            {"costAmount": "0", "budgetAmount": 30000, "currencyCode": "KRW"},
        ),
        _budget_cloudevent(
            {"costAmount": -1, "budgetAmount": 30000, "currencyCode": "KRW"},
        ),
        _budget_cloudevent(
            {"costAmount": 1, "budgetAmount": 30000, "currencyCode": "USD"},
        ),
        _budget_cloudevent(
            {
                "costAmount": 1,
                "budgetAmount": 30000,
                "currencyCode": "KRW",
                "forecastAmount": "26000",
            },
        ),
    ]

    assert malformed_envelopes
    terraform = _terraform()
    reject_terms = (
        "eventarc_pubsub_message_data_must_be_base64_json",
        "missing_costAmount",
        "costAmount_must_be_numeric",
        "costAmount_must_be_nonnegative",
        "wrong_currency",
        "forecastAmount_must_be_numeric_when_present",
    )
    for term in reject_terms:
        assert term in terraform
        assert terraform.index(term) < terraform.index("writeProviderStateReceipt")


def test_cost_cutoff_timer_events_remain_separate_from_budget_envelopes() -> None:
    timer_event = {
        "data": {
            "triggerKind": "timer",
            "thresholdBasis": "DURABLE_STATE_TIMER",
        }
    }

    terraform = _terraform()
    assert timer_event["data"]["triggerKind"] == "timer"
    assert "readLatestDurableState" in terraform
    assert "timer_requires_last_durable_budget_provider_state" in terraform
    assert terraform.index("trigger_kind == \"timer\"") < terraform.index(
        "decodeBudgetPubsubCloudEvent"
    )


def test_cost_cutoff_duplicate_lease_retries_until_terminal_success() -> None:
    terraform = _terraform()
    assert "status: in_progress" in terraform
    assert "inspectTerminalReceiptForDuplicate" in terraform
    assert "duplicate_terminal_success" in terraform
    assert 'terminal_success: "true"' in terraform
    assert "terminal_receipt_success" in terraform
    assert "retryDuplicateNonTerminal" in terraform
    assert terraform.index("inspectTerminalReceiptForDuplicate") < terraform.index(
        "stop_compute_before_disable_billing"
    )
    assert terraform.index("retryDuplicateNonTerminal") < terraform.index(
        "stop_compute_before_disable_billing"
    )


def test_cost_cutoff_iam_is_dedicated_and_least_privilege_without_opscat_mutation() -> None:
    terraform = _terraform()
    assert 'account_id   = "p176-cost-cutoff-workflow"' in terraform
    assert 'account_id   = "p176-cost-cutoff-eventarc"' in terraform
    assert 'account_id   = "p176-cost-cutoff-scheduler"' in terraform
    assert 'role_id     = "p176CostCutoffLabController"' in terraform
    for permission in (
        "compute.instances.get",
        "compute.instances.list",
        "compute.instances.stop",
        "compute.zoneOperations.get",
        "resourcemanager.projects.get",
        "billing.resourceAssociations.get",
        "billing.resourceAssociations.delete",
    ):
        assert permission in terraform
    assert "roles/eventarc.eventReceiver" in terraform
    assert "roles/workflows.invoker" in terraform
    assert "roles/logging.logWriter" in terraform
    assert "roles/storage.objectCreator" in terraform
    assert "roles/storage.objectViewer" in terraform
    assert "opscat" not in "\n".join(
        line for line in terraform.splitlines() if "iam_member" in line and "p176" not in line
    )


def test_live_lab_consumes_admin_topic_without_owning_budget() -> None:
    live_tf = _terraform(LIVE)
    assert "cost_cutoff_budget_topic_name" in live_tf
    assert "Reviewed external admin project" in live_tf
    assert "google_billing_budget" not in live_tf
    assert "google_monitoring_notification_channel" not in live_tf
    assert "project_number" not in live_tf
    assert "opscat-p176-admin-" in _read(LIVE / "terraform.tfvars.template")
    assert "cost_cutoff_budget_topic_name" in _read(LIVE / "terraform.tfvars.example")


def test_cost_cutoff_scripts_are_fail_closed_reviewed_plan_only() -> None:
    deploy = _read(CUTOFF / "deploy.sh")
    destroy = _read(CUTOFF / "destroy.sh")
    preflight = _read(CUTOFF / "preflight.sh")
    for script in (deploy, destroy, preflight):
        assert "set -euo pipefail" in script
        assert "EXPECTED_ADMIN_PROJECT_ID" in script
        assert "EXPECTED_LAB_PROJECT_ID" in script
        assert "opscat-p176-admin-" in script
        assert "opscat-p176-live-" in script
        assert "forbidden_patterns" in script
        assert "--auto-approve" not in script
        assert "services enable" not in script
        assert "projects create" not in script
    assert "APPLY_REVIEWED_PLAN" in deploy
    assert "EXPECTED_PLAN_SHA256" in deploy
    assert "declared_org" in deploy
    assert "declared_billing" in deploy
    assert "p176-cost-cutoff.tfplan.json" in deploy
    assert "verify-apply-plan.jq" in deploy
    assert 'terraform -chdir="${SCRIPT_DIR}" apply "p176-cost-cutoff.tfplan"' in deploy
    assert "APPLY_REVIEWED_DESTROY" in destroy
    assert "declared_org" in destroy
    assert "declared_billing" in destroy
    assert "p176-cost-cutoff-destroy.tfplan.json" in destroy
    assert "verify-destroy-plan.jq" in destroy
    assert 'terraform -chdir="${SCRIPT_DIR}" apply "p176-cost-cutoff-destroy.tfplan"' in destroy
    assert "P176_CUTOFF_PREFLIGHT_RUN_PLAN" in preflight
    assert "plan -refresh=false" in deploy
    assert "plan -destroy -refresh=false" in destroy
    assert "plan -refresh=false" in preflight
    assert "apply_attempted: false" in preflight
    assert "destroy_attempted: false" in preflight


def test_cost_cutoff_deploy_refuses_reusing_an_attempted_reviewed_plan() -> None:
    deploy = _read(CUTOFF / "deploy.sh")

    assert "p176-cost-cutoff-apply-attempt.json" in deploy
    assert "attempted_plan_sha256" in deploy
    assert "Refusing apply: this reviewed plan digest already has an apply attempt receipt." in deploy
    assert "set -o noclobber" in deploy
    assert 'if ! : >"${APPLY_ATTEMPT_RECEIPT}"' in deploy
    assert "apply_started_at" in deploy
    assert 'write_apply_attempt_receipt "started"' in deploy
    assert 'write_apply_attempt_receipt "failed"' in deploy
    assert 'write_apply_attempt_receipt "succeeded"' in deploy
    assert 'terraform -chdir="${SCRIPT_DIR}" apply "p176-cost-cutoff.tfplan"' in deploy


def test_cost_cutoff_deploy_enforces_one_apply_attempt_per_plan_digest(
    tmp_path: Path,
) -> None:
    stack = tmp_path / "stack"
    fake_bin = tmp_path / "bin"
    stack.mkdir()
    fake_bin.mkdir()
    shutil.copy2(CUTOFF / "deploy.sh", stack / "deploy.sh")
    shutil.copy2(CUTOFF / "verify-apply-plan.jq", stack / "verify-apply-plan.jq")
    (stack / "terraform.tfvars").write_text(
        "\n".join(
            (
                f'admin_project_id = "{ADMIN_PROJECT}"',
                f'org_id = "{ORG_ID}"',
                f'lab_project_id = "{LAB_PROJECT}"',
                f'billing_account_id = "{BILLING_ACCOUNT}"',
                'budget_alert_email = "alerts@example.invalid"',
            )
        ),
        encoding="utf-8",
    )
    plan_json = tmp_path / "valid-plan.json"
    plan_json.write_text(json.dumps(_valid_apply_plan()), encoding="utf-8")
    apply_log = tmp_path / "apply.log"
    fake_terraform = fake_bin / "terraform"
    fake_terraform.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  case "${arg}" in
    show)
      cat "${FAKE_PLAN_JSON}"
      exit 0
      ;;
    apply)
      if [[ -f "${FAKE_EXPECTED_RECEIPT}" ]]; then
        printf 'apply receipt_present=true\\n' >>"${FAKE_APPLY_LOG}"
      else
        printf 'apply receipt_present=false\\n' >>"${FAKE_APPLY_LOG}"
      fi
      exit "${FAKE_APPLY_EXIT:-0}"
      ;;
  esac
done
exit 0
""",
        encoding="utf-8",
    )
    fake_terraform.chmod(0o755)

    plan = stack / "p176-cost-cutoff.tfplan"
    sidecar = stack / "p176-cost-cutoff.tfplan.sha256"

    def run_apply(plan_bytes: bytes, *, exit_code: int) -> tuple[subprocess.CompletedProcess[str], Path]:
        plan.write_bytes(plan_bytes)
        digest = hashlib.sha256(plan_bytes).hexdigest()
        sidecar.write_text(f"{digest}  {plan}\n", encoding="utf-8")
        receipt = stack / ".terraform" / "p176-cost-cutoff-apply-attempts" / f"{digest}.json"
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fake_bin}:{env['PATH']}",
                "EXPECTED_ADMIN_PROJECT_ID": ADMIN_PROJECT,
                "EXPECTED_LAB_PROJECT_ID": LAB_PROJECT,
                "TFVARS_FILE": str(stack / "terraform.tfvars"),
                "APPLY_REVIEWED_PLAN": "1",
                "EXPECTED_PLAN_SHA256": digest,
                "FAKE_PLAN_JSON": str(plan_json),
                "FAKE_APPLY_LOG": str(apply_log),
                "FAKE_EXPECTED_RECEIPT": str(receipt),
                "FAKE_APPLY_EXIT": str(exit_code),
            }
        )
        result = subprocess.run(
            ["bash", str(stack / "deploy.sh")],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, receipt

    failed, failed_receipt = run_apply(b"reviewed-plan-one", exit_code=23)
    assert failed.returncode == 23
    assert apply_log.read_text(encoding="utf-8").splitlines() == [
        "apply receipt_present=true"
    ]
    failed_payload = json.loads(failed_receipt.read_text(encoding="utf-8"))
    assert failed_payload["status"] == "failed"
    assert failed_payload["exit_code"] == 23
    assert set(failed_payload) == {
        "plan_sha256",
        "apply_started_at",
        "apply_finished_at",
        "status",
        "exit_code",
        "contains_cloud_identifiers",
    }
    assert failed_payload["contains_cloud_identifiers"] is False
    serialized_receipt = json.dumps(failed_payload)
    for sensitive_value in (ADMIN_PROJECT, LAB_PROJECT, ORG_ID, BILLING_ACCOUNT):
        assert sensitive_value not in serialized_receipt

    repeated, repeated_receipt = run_apply(b"reviewed-plan-one", exit_code=0)
    assert repeated.returncode != 0
    assert repeated_receipt == failed_receipt
    assert "already has an apply attempt receipt" in repeated.stderr
    assert apply_log.read_text(encoding="utf-8").splitlines() == [
        "apply receipt_present=true"
    ]

    fresh, fresh_receipt = run_apply(b"reviewed-plan-two", exit_code=0)
    assert fresh.returncode == 0
    assert fresh_receipt != failed_receipt
    assert apply_log.read_text(encoding="utf-8").splitlines() == [
        "apply receipt_present=true",
        "apply receipt_present=true",
    ]
    fresh_payload = json.loads(fresh_receipt.read_text(encoding="utf-8"))
    assert fresh_payload["status"] == "succeeded"
    assert fresh_payload["exit_code"] == 0


def test_cost_cutoff_plan_guard_accepts_only_control_plane_shape() -> None:
    assert _run_jq_guard("verify-apply-plan.jq", _valid_apply_plan()).returncode == 0


def test_cost_cutoff_plan_guard_accepts_same_plan_computed_budget_links() -> None:
    plan = _valid_apply_plan()
    budget = _find_change(plan, "google_billing_budget", "lab")["change"]
    del budget["after"]["budget_filter"][0]["projects"]
    del budget["after"]["all_updates_rule"][0]["pubsub_topic"]
    budget["after_unknown"] = {
        "budget_filter": [{"projects": True}],
        "all_updates_rule": [{"pubsub_topic": True}],
    }

    assert _run_jq_guard("verify-apply-plan.jq", plan).returncode == 0


def test_cost_cutoff_plan_guard_rejects_unsafe_shapes() -> None:
    cases: list[dict[str, Any]] = []

    wildcard = _valid_apply_plan()
    wildcard["resource_changes"].append(
        _change(
            "google_project_iam_member",
            "wildcard",
            {"project": ADMIN_PROJECT, "role": "roles/viewer", "member": "user:*"},
        )
    )
    cases.append(wildcard)

    owner = _valid_apply_plan()
    _find_change(owner, "google_project_iam_member", "workflow_log_writer")["change"]["after"]["role"] = "roles/owner"
    cases.append(owner)

    editor = _valid_apply_plan()
    _find_change(editor, "google_project_iam_member", "workflow_log_writer")["change"]["after"]["role"] = "roles/editor"
    cases.append(editor)

    key = _valid_apply_plan()
    key["resource_changes"].append(
        _change("google_service_account_key", "bad", {"project": ADMIN_PROJECT})
    )
    cases.append(key)

    lab_controller = _valid_apply_plan()
    _find_change(lab_controller, "google_project_iam_custom_role", "lab_controller")["change"]["after"]["project"] = ADMIN_PROJECT
    cases.append(lab_controller)

    wrong_workflow = _valid_apply_plan()
    _find_change(wrong_workflow, "google_workflows_workflow", "cutoff")["change"]["after"]["source_contents"] = "disable first"
    cases.append(wrong_workflow)

    extra_project = _valid_apply_plan()
    extra_project["resource_changes"].append(
        _change(
            "google_project",
            "extra",
            {
                "project_id": "opscat-p176-admin-extra1",
                "name": "opscat-p176-admin-extra1",
                "org_id": ORG_ID,
                "billing_account": BILLING_ACCOUNT,
                "auto_create_network": False,
                "deletion_policy": "DELETE",
            },
        )
    )
    cases.append(extra_project)

    auto_network = _valid_apply_plan()
    _find_change(auto_network, "google_project", "admin")["change"]["after"]["auto_create_network"] = True
    cases.append(auto_network)

    shared_vpc = _valid_apply_plan()
    shared_vpc["resource_changes"].append(
        _change("google_compute_shared_vpc_host_project", "bad", {"project": ADMIN_PROJECT})
    )
    cases.append(shared_vpc)

    org_iam = _valid_apply_plan()
    org_iam["resource_changes"].append(
        _change("google_organization_iam_member", "bad", {"org_id": ORG_ID, "role": "roles/viewer", "member": "user:test@example.com"})
    )
    cases.append(org_iam)

    folder_iam = _valid_apply_plan()
    folder_iam["resource_changes"].append(
        _change("google_folder_iam_member", "bad", {"folder": "folders/123", "role": "roles/viewer", "member": "user:test@example.com"})
    )
    cases.append(folder_iam)

    public_bucket = _valid_apply_plan()
    _find_change(public_bucket, "google_storage_bucket", "receipts")["change"]["after"]["public_access_prevention"] = "inherited"
    cases.append(public_bucket)

    extra_service = _valid_apply_plan()
    extra_service["resource_changes"].append(
        _change("google_project_service", "admin", {"project": ADMIN_PROJECT, "service": "cloudresourcemanager.googleapis.com"})
    )
    cases.append(extra_service)

    for plan in cases:
        assert _run_jq_guard("verify-apply-plan.jq", plan).returncode != 0


def test_cost_cutoff_destroy_guard_delete_only_and_foreign_project_rejection() -> None:
    valid = _valid_destroy_plan()
    assert _run_jq_guard("verify-destroy-plan.jq", valid).returncode == 0

    create = deepcopy(valid)
    create["resource_changes"][0]["change"]["actions"] = ["create"]
    assert _run_jq_guard("verify-destroy-plan.jq", create).returncode != 0

    foreign = deepcopy(valid)
    foreign["resource_changes"][2]["change"]["before"]["project"] = "prod-forbidden-project"
    assert _run_jq_guard("verify-destroy-plan.jq", foreign).returncode != 0

    missing_project_delete = deepcopy(valid)
    missing_project_delete["resource_changes"] = [
        change for change in missing_project_delete["resource_changes"] if change["type"] != "google_project"
    ]
    assert _run_jq_guard("verify-destroy-plan.jq", missing_project_delete).returncode != 0

    wrong_project_delete = deepcopy(valid)
    wrong_project_delete["resource_changes"][-1]["change"]["before"]["project_id"] = "opscat-p176-admin-foreign"
    assert _run_jq_guard("verify-destroy-plan.jq", wrong_project_delete).returncode != 0


def test_cost_cutoff_destroy_guard_rejects_unrelated_billing_budget_delete() -> None:
    plan = _valid_destroy_plan()
    plan["resource_changes"].append(
        {
            "address": "google_billing_budget.unrelated_team_budget",
            "type": "google_billing_budget",
            "name": "unrelated_team_budget",
            "change": {
                "actions": ["delete"],
                "before": {
                    "billing_account": BILLING_ACCOUNT,
                    "display_name": "unrelated team budget",
                    "budget_filter": [{"projects": ["projects/999999"]}],
                },
                "after": None,
            },
        }
    )

    assert _run_jq_guard("verify-destroy-plan.jq", plan).returncode != 0


def test_cost_cutoff_destroy_guard_requires_module_owned_billing_budget() -> None:
    wrong_budget = _valid_destroy_plan()
    budget_change = _find_change(wrong_budget, "google_billing_budget", "lab")
    budget_change["address"] = "google_billing_budget.shared_lab"
    budget_change["name"] = "shared_lab"
    budget_change["change"]["before"]["display_name"] = "shared lab budget"

    assert _run_jq_guard("verify-destroy-plan.jq", wrong_budget).returncode != 0


def test_cost_cutoff_destroy_guard_rejects_budget_filter_bound_to_foreign_project_number() -> None:
    valid = _valid_destroy_plan()
    assert _run_jq_guard("verify-destroy-plan.jq", valid).returncode == 0

    foreign_budget_filter = deepcopy(valid)
    budget_change = _find_change(foreign_budget_filter, "google_billing_budget", "lab")
    budget_change["change"]["before"]["budget_filter"][0]["projects"] = ["projects/999999"]

    assert _run_jq_guard("verify-destroy-plan.jq", foreign_budget_filter).returncode != 0


def test_live_preflight_public_evidence_uses_logical_repo_relative_paths() -> None:
    local_absolute_path = re.compile(
        r"(/Users/|/private/|/var/folders/|/tmp/|[A-Za-z]:\\)"
    )
    public_evidence_files = [
        path
        for path in P176_EVIDENCE.rglob("*")
        if path.is_file() and ".tmp." not in path.name
    ]

    assert public_evidence_files
    for path in public_evidence_files:
        assert not local_absolute_path.search(_read(path)), path.relative_to(ROOT)


def test_live_preflight_allows_benign_human_gcloud_account_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "gcloud"
    config_dir.mkdir(parents=True)
    (config_dir / "credentials.db").write_text(
        "configured_account=user@example.test\nrefresh_token=redacted\n",
        encoding="utf-8",
    )
    (config_dir / "access_tokens.db").write_text("access_token=ya29.redacted\n", encoding="utf-8")
    (config_dir / "application_default_credentials.json").write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "redacted",
                "client_secret": "redacted",
                "refresh_token": "redacted",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "configurations").mkdir()
    (config_dir / "configurations" / "config_default").write_text(
        "[core]\naccount = user@example.test\nproject = opscat-p176-live-test01\n",
        encoding="utf-8",
    )
    for store in (
        config_dir / "credentials.db",
        config_dir / "access_tokens.db",
        config_dir / "application_default_credentials.json",
        config_dir / "configurations" / "config_default",
    ):
        store.chmod(0o600)

    result = _run_live_preflight(tmp_path, home=home)

    readiness = json.loads((tmp_path / "artifacts" / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 0
    assert readiness["status"] == "ready_for_plan_generation"
    assert "possible_persisted_gcloud_credential_or_account_content" not in readiness["blocking_reasons"]
    assert "possible_persisted_service_account_key_filename" not in readiness["blocking_reasons"]


def test_live_preflight_rejects_adc_service_account_private_key_material(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "gcloud"
    config_dir.mkdir(parents=True)
    (config_dir / "application_default_credentials.json").write_text(
        json.dumps(
            {
                "type": "service_account",
                "private_key_id": "redacted-test-key-id",
                "private_key": "-----BEGIN PRIVATE KEY-----\nREDACTED\n-----END PRIVATE KEY-----\n",
                "client_email": "svc@example.test",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )

    result = _run_live_preflight(tmp_path, home=home)

    readiness = json.loads((tmp_path / "artifacts" / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 2
    assert "unsafe_gcloud_adc_service_account_key_material" in readiness["blocking_reasons"]


def test_live_preflight_rejects_permissive_known_gcloud_store(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "gcloud"
    config_dir.mkdir(parents=True)
    credential_store = config_dir / "credentials.db"
    credential_store.write_text("refresh_token=redacted\n", encoding="utf-8")
    credential_store.chmod(0o644)

    result = _run_live_preflight(tmp_path, home=home)

    readiness = json.loads((tmp_path / "artifacts" / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 2
    assert "unsafe_gcloud_credential_store_permissions" in readiness["blocking_reasons"]


def test_live_preflight_rejects_symlinked_known_gcloud_store(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "gcloud"
    config_dir.mkdir(parents=True)
    target = tmp_path / "credential-target.db"
    target.write_text("refresh_token=redacted\n", encoding="utf-8")
    (config_dir / "credentials.db").symlink_to(target)

    result = _run_live_preflight(tmp_path, home=home)

    readiness = json.loads((tmp_path / "artifacts" / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 2
    assert "unsafe_gcloud_credential_store_symlink" in readiness["blocking_reasons"]


def test_live_preflight_rejects_unexpected_gcloud_token_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "gcloud"
    config_dir.mkdir(parents=True)
    (config_dir / "legacy-token.json").write_text(json.dumps({"refresh_token": "redacted"}), encoding="utf-8")

    result = _run_live_preflight(tmp_path, home=home)

    readiness = json.loads((tmp_path / "artifacts" / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 2
    assert "possible_persisted_gcloud_credential_or_account_content" in readiness["blocking_reasons"]


def test_live_preflight_rejects_unexpected_gcloud_service_account_key_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "gcloud"
    config_dir.mkdir(parents=True)
    (config_dir / "service-account-key.json").write_text(
        json.dumps(
            {
                "type": "service_account",
                "private_key_id": "redacted-test-key-id",
                "private_key": "-----BEGIN PRIVATE KEY-----\nREDACTED\n-----END PRIVATE KEY-----\n",
                "client_email": "svc@example.test",
            }
        ),
        encoding="utf-8",
    )

    result = _run_live_preflight(tmp_path, home=home)

    readiness = json.loads((tmp_path / "artifacts" / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 2
    assert "possible_persisted_gcloud_credential_or_account_content" in readiness["blocking_reasons"]
    assert "possible_persisted_service_account_key_filename" in readiness["blocking_reasons"]


def test_live_preflight_public_artifact_scan_remains_strict_for_identifiers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "seed-public-evidence.json").write_text(
        json.dumps(
            {
                "operator": "user@example.test",
                "billing": "billingAccounts/ABCDEF-123456-789ABC",
                "org": "organizations/123456789012",
                "project": LAB_PROJECT,
                "path": str(tmp_path / "local" / "file.json"),
            }
        ),
        encoding="utf-8",
    )

    result = _run_live_preflight(tmp_path, home=home, artifact_dir=artifact_dir)

    readiness = json.loads((artifact_dir / "p176-live-preflight-readiness.json").read_text())
    assert result.returncode == 2
    assert "generated_artifact_sensitive_content_detected" in readiness["blocking_reasons"]


def test_p176_required_safe_tfvars_templates_are_git_addable() -> None:
    safe_tfvars_inputs = [
        "infra/gcp/p176-live/terraform.tfvars.example",
        "infra/gcp/p176-live/terraform.tfvars.template",
        "infra/gcp/p176-cost-cutoff/terraform.tfvars.example",
        "infra/gcp/p176-cost-cutoff/terraform.tfvars.template",
    ]
    private_tfvars_inputs = [
        "infra/gcp/p176-live/terraform.tfvars",
        "infra/gcp/p176-cost-cutoff/terraform.tfvars",
    ]

    for path in safe_tfvars_inputs:
        assert _git_check_ignore(path).returncode == 1, path
    for path in private_tfvars_inputs:
        assert _git_check_ignore(path).returncode == 0, path


def test_cost_cutoff_architecture_doc_names_external_authorization_and_budget_limits() -> None:
    doc = _read(DOC)
    assert "Budgets are not hard caps" in doc
    assert "external authorization" in doc
    assert "admin project" in doc
    assert "creates exactly two fresh projects" in doc
    assert "auto_create_network=false" in doc
    assert "deletion_policy=DELETE" in doc
    assert "lab project" in doc
    assert "stop compute before disabling billing" in doc
    assert "24,000 KRW" in doc
    assert "27,000 KRW" in doc
    assert "30,000 KRW" in doc
    assert "stale after 600 seconds" in doc
    assert "36 hours" in doc
    assert "48 hours" in doc
    assert "must not run inside the lab project" in doc


def _change(resource_type: str, name: str, after: dict[str, Any]) -> dict[str, Any]:
    return {
        "address": f"{resource_type}.{name}",
        "type": resource_type,
        "name": name,
        "change": {"actions": ["create"], "before": None, "after": after},
    }


def _find_change(plan: dict[str, Any], resource_type: str, name: str) -> dict[str, Any]:
    for change in plan["resource_changes"]:
        if change["type"] == resource_type and change["name"] == name:
            return change
    raise AssertionError(f"missing {resource_type}.{name}")


def _budget_cloudevent(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "specversion": "1.0",
        "id": "1234567890",
        "source": f"//pubsub.googleapis.com/projects/{ADMIN_PROJECT}/topics/p176-cost-cutoff-budget",
        "type": "google.cloud.pubsub.topic.v1.messagePublished",
        "time": "2026-07-19T00:00:00Z",
        "data": {
            "message": {
                "data": base64.b64encode(
                    json.dumps(payload).encode("utf-8")
                ).decode("ascii"),
                "messageId": "budget-message-1",
                "publishTime": "2026-07-19T00:00:00Z",
            },
            "subscription": f"projects/{ADMIN_PROJECT}/subscriptions/eventarc",
        },
    }


def _decoded_budget_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    encoded = envelope["data"]["message"]["data"]
    decoded = base64.b64decode(encoded).decode("utf-8")
    payload = json.loads(decoded)
    assert isinstance(payload, dict)
    return payload


def _valid_apply_plan() -> dict[str, Any]:
    return {
        "variables": {
            "admin_project_id": {"value": ADMIN_PROJECT},
            "org_id": {"value": ORG_ID},
            "lab_project_id": {"value": LAB_PROJECT},
            "billing_account_id": {"value": BILLING_ACCOUNT},
            "soft_stop_krw": {"value": 24000},
            "hard_cutoff_krw": {"value": 27000},
            "budget_krw": {"value": 30000},
        },
        "resource_changes": [
            _change(
                "google_project",
                "admin",
                {
                    "project_id": ADMIN_PROJECT,
                    "name": ADMIN_PROJECT,
                    "org_id": ORG_ID,
                    "billing_account": BILLING_ACCOUNT,
                    "auto_create_network": False,
                    "deletion_policy": "DELETE",
                },
            ),
            _change(
                "google_project",
                "lab",
                {
                    "project_id": LAB_PROJECT,
                    "name": LAB_PROJECT,
                    "org_id": ORG_ID,
                    "billing_account": BILLING_ACCOUNT,
                    "auto_create_network": False,
                    "deletion_policy": "DELETE",
                },
            ),
            *[
                _change("google_project_service", "admin", {"project": ADMIN_PROJECT, "service": service})
                for service in (
                    "cloudbilling.googleapis.com",
                    "cloudscheduler.googleapis.com",
                    "compute.googleapis.com",
                    "eventarc.googleapis.com",
                    "iam.googleapis.com",
                    "logging.googleapis.com",
                    "pubsub.googleapis.com",
                    "serviceusage.googleapis.com",
                    "storage.googleapis.com",
                    "workflows.googleapis.com",
                )
            ],
            *[
                _change("google_project_service", "lab", {"project": LAB_PROJECT, "service": service})
                for service in (
                    "billingbudgets.googleapis.com",
                    "compute.googleapis.com",
                    "iam.googleapis.com",
                    "iap.googleapis.com",
                    "logging.googleapis.com",
                    "monitoring.googleapis.com",
                    "oslogin.googleapis.com",
                )
            ],
            _change("google_pubsub_topic", "budget_notifications", {"project": ADMIN_PROJECT, "name": "p176-cost-cutoff-budget"}),
            _change(
                "google_monitoring_notification_channel",
                "budget_email",
                {"project": LAB_PROJECT, "display_name": "P176 live budget email"},
            ),
            _change(
                "google_billing_budget",
                "lab",
                {
                    "billing_account": BILLING_ACCOUNT,
                    "budget_filter": [{"projects": ["projects/176001"]}],
                    "amount": [
                        {
                            "specified_amount": [
                                {"currency_code": "KRW", "units": "30000"}
                            ]
                        }
                    ],
                    "all_updates_rule": [
                        {
                            "pubsub_topic": f"projects/{ADMIN_PROJECT}/topics/p176-cost-cutoff-budget",
                            "disable_default_iam_recipients": True,
                        }
                    ],
                },
            ),
            _change("google_eventarc_trigger", "budget_to_workflow", {"project": ADMIN_PROJECT, "name": "p176-cost-cutoff-budget-to-workflow"}),
            _change(
                "google_storage_bucket",
                "receipts",
                {
                    "project": ADMIN_PROJECT,
                    "name": f"{ADMIN_PROJECT}-p176-cost-cutoff-receipts",
                    "uniform_bucket_level_access": True,
                    "public_access_prevention": "enforced",
                },
            ),
            _change(
                "google_workflows_workflow",
                "cutoff",
                {
                    "project": ADMIN_PROJECT,
                    "name": "p176-cost-cutoff",
                    "source_contents": "\n".join(
                        (
                            "ifGenerationMatch: 0",
                            "readLatestDurableState",
                            "updateCanonicalLatestStateAtomically",
                            "fail_closed_missing_budget_provider_state",
                            "fail_closed_stale_budget_provider_state",
                            "forecast_amount_krw * 1.15",
                            "duplicate_terminal_success",
                            "alreadyExists",
                            "stop_compute_before_disable_billing",
                            "googleapis.compute.v1.instances.stop",
                            "googleapis.cloudbilling.v1.projects.updateBillingInfo",
                            "billingAccountName: null",
                        )
                    ),
                },
            ),
            _change("google_service_account", "workflow", {"project": ADMIN_PROJECT, "account_id": "p176-cost-cutoff-workflow"}),
            _change(
                "google_project_iam_member",
                "workflow_log_writer",
                {
                    "project": ADMIN_PROJECT,
                    "role": "roles/logging.logWriter",
                    "member": f"serviceAccount:{'p176-cost-cutoff-workflow'}@{ADMIN_PROJECT}.{'iam.gserviceaccount.com'}",
                },
            ),
            _change(
                "google_project_iam_custom_role",
                "lab_controller",
                {
                    "project": LAB_PROJECT,
                    "role_id": "p176CostCutoffLabController",
                    "permissions": [
                        "compute.instances.get",
                        "compute.instances.list",
                        "compute.instances.stop",
                        "compute.zoneOperations.get",
                        "resourcemanager.projects.get",
                        "billing.resourceAssociations.get",
                        "billing.resourceAssociations.delete",
                    ],
                },
            ),
        ],
    }


def _valid_destroy_plan() -> dict[str, Any]:
    return {
        "variables": {
            "admin_project_id": {"value": ADMIN_PROJECT},
            "org_id": {"value": ORG_ID},
            "lab_project_id": {"value": LAB_PROJECT},
            "billing_account_id": {"value": BILLING_ACCOUNT},
        },
        "resource_changes": [
            {
                "address": "google_pubsub_topic.budget_notifications",
                "type": "google_pubsub_topic",
                "name": "budget_notifications",
                "change": {
                    "actions": ["delete"],
                    "before": {"project": ADMIN_PROJECT, "name": "p176-cost-cutoff-budget"},
                    "after": None,
                },
            },
            {
                "address": "google_project_iam_custom_role.lab_controller",
                "type": "google_project_iam_custom_role",
                "name": "lab_controller",
                "change": {
                    "actions": ["delete"],
                    "before": {"project": LAB_PROJECT, "role_id": "p176CostCutoffLabController"},
                    "after": None,
                },
            },
            {
                "address": "google_project_service.lab[\"compute.googleapis.com\"]",
                "type": "google_project_service",
                "name": "lab",
                "change": {
                    "actions": ["delete"],
                    "before": {"project": LAB_PROJECT, "service": "compute.googleapis.com"},
                    "after": None,
                },
            },
            {
                "address": "google_monitoring_notification_channel.budget_email",
                "type": "google_monitoring_notification_channel",
                "name": "budget_email",
                "change": {
                    "actions": ["delete"],
                    "before": {"project": LAB_PROJECT, "display_name": "P176 live budget email"},
                    "after": None,
                },
            },
            {
                "address": "google_billing_budget.lab",
                "type": "google_billing_budget",
                "name": "lab",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "billing_account": BILLING_ACCOUNT,
                        "display_name": "P176 disposable live lab budget",
                        "budget_filter": [{"projects": ["projects/176001"]}],
                    },
                    "after": None,
                },
            },
            {
                "address": "google_storage_bucket.receipts",
                "type": "google_storage_bucket",
                "name": "receipts",
                "change": {
                    "actions": ["delete"],
                    "before": {"project": ADMIN_PROJECT, "name": f"{ADMIN_PROJECT}-p176-cost-cutoff-receipts"},
                    "after": None,
                },
            },
            {
                "address": "google_project.admin",
                "type": "google_project",
                "name": "admin",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "project_id": ADMIN_PROJECT,
                        "name": ADMIN_PROJECT,
                        "org_id": ORG_ID,
                        "billing_account": BILLING_ACCOUNT,
                        "auto_create_network": False,
                        "deletion_policy": "DELETE",
                    },
                    "after": None,
                },
            },
            {
                "address": "google_project.lab",
                "type": "google_project",
                "name": "lab",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "project_id": LAB_PROJECT,
                        "number": "176001",
                        "name": LAB_PROJECT,
                        "org_id": ORG_ID,
                        "billing_account": BILLING_ACCOUNT,
                        "auto_create_network": False,
                        "deletion_policy": "DELETE",
                    },
                    "after": None,
                },
            },
        ],
    }


def _run_jq_guard(name: str, plan: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "jq",
            "-e",
            "--arg",
            "admin_project",
            ADMIN_PROJECT,
            "--arg",
            "lab_project",
            LAB_PROJECT,
            "-f",
            str(CUTOFF / name),
        ],
        input=json.dumps(plan),
        text=True,
        capture_output=True,
        check=False,
    )


def _run_live_preflight(
    tmp_path: Path,
    *,
    home: Path,
    artifact_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    artifact_dir = artifact_dir or tmp_path / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    tfvars = tmp_path / "terraform.tfvars"
    tfvars.write_text(
        '\n'.join(
            (
                f'project_id = "{LAB_PROJECT}"',
                f'billing_account_id = "{BILLING_ACCOUNT}"',
                "",
            )
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_terraform(bin_dir / "terraform")
    _write_fake_gcloud(bin_dir / "gcloud")

    env = {
        **os.environ,
        "ARTIFACT_DIR": str(artifact_dir),
        "EXPECTED_PROJECT_ID": LAB_PROJECT,
        "EXPECTED_BILLING_ACCOUNT_ID": BILLING_ACCOUNT,
        "HOME": str(home),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TFVARS_FILE": str(tfvars),
        "P176_PREFLIGHT_RUN_PLAN": "0",
    }
    return subprocess.run(
        ["bash", str(LIVE / "preflight.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_fake_terraform(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *" version") printf 'Terraform v1.0.0\\n' ;;
  *" fmt -check") exit 0 ;;
  *" validate") printf 'Success!\\n' ;;
  *) exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _write_fake_gcloud(path: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "--version") printf 'Google Cloud SDK 999.0.0\\n' ;;
  "config list --format=json") printf '%s\\n' '{{"core":{{"project":"{LAB_PROJECT}"}}}}' ;;
  "auth list --filter=status:ACTIVE --format=json") printf '%s\\n' '[{{"account":"user@example.test","status":"ACTIVE"}}]' ;;
  "billing accounts list --format=json") printf '%s\\n' '[{{"name":"billingAccounts/{BILLING_ACCOUNT}","open":true}}]' ;;
  *) exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _git_check_ignore(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
