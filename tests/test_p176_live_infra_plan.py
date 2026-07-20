from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "gcp" / "p176-live"
FORBIDDEN_PROJECTS = {
    "prod",
    "production",
    "shared-vpc",
}
OWNER_EMAIL = "owner" + "@" + "example.invalid"
PERSISTED_ADMIN_EMAIL = "persisted-admin" + "@" + "example.invalid"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _terraform() -> str:
    return "\n".join(_read(path) for path in INFRA.glob("*.tf"))


def test_p176_live_module_clones_p174_disposable_project_controls() -> None:
    required = {
        "versions.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "terraform.tfvars.template",
        "target-startup.sh",
        "observer-startup.sh",
        "README.md",
        "deploy.sh",
        "destroy.sh",
        "preflight.sh",
        "verify-apply-plan.jq",
        "verify-destroy-plan.jq",
    }
    assert required <= {path.name for path in INFRA.iterdir() if path.is_file()}

    terraform = _terraform()
    assert 'resource "google_project" "p176_live"' not in terraform
    assert "google_project_service" not in terraform
    assert "deletion_policy" not in terraform
    assert "auto_create_network = false" not in terraform
    assert "project_number" not in terraform
    assert "google_billing_budget" not in terraform
    assert "google_monitoring_notification_channel" not in terraform
    assert "budget_amount_krw" not in terraform
    assert f'default     = "{BILLING_ACCOUNT_ID}"' not in terraform
    assert 'default     = "000000000000"' not in terraform
    assert "var.billing_account_id ==" not in terraform
    assert "organization_id" not in terraform
    assert "project_name" not in terraform
    assert 'purpose                 = "p176-live-lab"' in terraform
    assert 'owner                   = "kdh"' in terraform
    assert 'ticket                  = "p176-live-001"' in terraform
    assert 'expected_project_prefix = "opscat-p176-live-"' in terraform
    assert 'can(regex("^opscat-p176-live-[a-z0-9-]{6,20}$", var.project_id))' in terraform
    assert "google_billing_project_info" not in terraform
    assert "roles/owner" not in terraform
    assert "roles/editor" not in terraform
    assert "service_account_key" not in terraform
    for forbidden in FORBIDDEN_PROJECTS:
        assert forbidden not in terraform


def test_p176_live_network_is_private_vpc_and_iap_only() -> None:
    terraform = _terraform()
    assert 'name                    = "p176-live-vpc"' in terraform
    assert 'auto_create_subnetworks = false' in terraform
    assert 'private_ip_google_access = true' in terraform
    assert "35.235.240.0/20" in terraform
    assert "roles/iap.tunnelResourceAccessor" in terraform
    assert "roles/compute.osAdminLogin" in terraform
    assert 'source_ranges = ["0.0.0.0/0"]' not in terraform
    assert "access_config" not in terraform
    assert 'network_ip = "10.176.0.10"' in terraform
    assert 'network_ip = "10.176.0.20"' in terraform
    assert 'name                    = "default"' not in terraform
    assert 'auto_create_subnetworks = true' not in terraform


def test_p176_live_network_has_bounded_cloud_nat_and_web_dns_egress_only() -> None:
    terraform = _terraform()
    assert 'resource "google_compute_router" "p176_live"' in terraform
    assert 'resource "google_compute_router_nat" "p176_live"' in terraform
    assert 'name    = "p176-live-router"' in terraform
    assert 'name                               = "p176-live-nat"' in terraform
    assert 'nat_ip_allocate_option             = "AUTO_ONLY"' in terraform
    assert 'source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"' in terraform
    assert "google_compute_subnetwork.p176_live.id" in terraform
    assert 'source_ip_ranges_to_nat = ["ALL_IP_RANGES"]' in terraform
    assert 'filter = "ERRORS_ONLY"' in terraform
    assert terraform.count("google_compute_firewall.bounded_web_dns_egress") == 2
    assert terraform.count("google_compute_firewall.deny_other_egress") == 2
    assert 'name    = "p176-live-bounded-web-dns-egress"' in terraform
    assert 'name    = "p176-live-deny-other-egress"' in terraform
    assert terraform.count('direction          = "EGRESS"') == 3
    assert 'resource "google_compute_firewall" "observer_to_target_private_egress"' in terraform
    assert 'name    = "p176-live-observer-to-target-private-egress"' in terraform
    assert 'destination_ranges = ["10.176.0.10/32"]' in terraform
    assert 'target_tags        = ["opscat-p176-live-observer"]' in terraform
    assert 'ports    = ["8000"]' in terraform
    assert 'ports    = ["8000", "8020", "9090", "3100"]' not in terraform
    assert 'ports    = ["53", "80", "443"]' in terraform
    assert 'ports    = ["53"]' in terraform
    assert 'protocol = "all"' in terraform
    assert 'priority           = 1000' in terraform
    assert 'priority           = 1100' in terraform
    assert "google_compute_address" not in terraform


def test_p176_live_identity_split_has_no_key_or_opscat_mutation_path() -> None:
    terraform = _terraform()
    assert 'account_id   = "p176-live-target"' in terraform
    assert 'account_id   = "p176-live-observer"' in terraform
    assert 'account_id   = "p176-live-harness-fault"' in terraform
    assert 'display_name = "P176 live harness fault injection and cleanup"' in terraform
    assert "roles/compute.viewer" in terraform
    assert "roles/logging.viewer" in terraform
    assert "roles/monitoring.viewer" in terraform
    assert "roles/iam.serviceAccountTokenCreator" not in terraform
    assert "roles/iam.serviceAccountUser" not in terraform
    assert "opscat_principal" in terraform
    assert "google_project_iam_member\" \"opscat" not in terraform
    assert "google_service_account_key" not in terraform


def test_p176_live_startup_blocks_container_metadata_and_sets_expiry() -> None:
    for name in ("target-startup.sh", "observer-startup.sh"):
        script = _read(INFRA / name)
        assert script.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in script
        assert "DOCKER-USER" in script
        assert "169.254.169.254/32" in script
        assert "p176-live-block-container-metadata.service" in script
        assert "-I DOCKER-USER 1 -d 169.254.169.254/32 -j REJECT" in script
        assert "gcloud auth activate-service-account" not in script
        assert "BEGIN PRIVATE KEY" not in script
        assert "NVIDIA_API_KEY" not in script
        assert "p176-live-expiry-shutdown.timer" in script
        assert "OnCalendar=2026-08-01 00:00:00 UTC" in script


def test_p176_live_deploy_and_destroy_are_reviewed_plan_only() -> None:
    deploy = _read(INFRA / "deploy.sh")
    destroy = _read(INFRA / "destroy.sh")
    apply_guard = _read(INFRA / "verify-apply-plan.jq")
    destroy_guard = _read(INFRA / "verify-destroy-plan.jq")
    for script in (deploy, destroy):
        assert "EXPECTED_PROJECT_ID" in script
        assert "EXPECTED_PROJECT_NUMBER" not in script
        assert "EXPECTED_BILLING_ACCOUNT_ID" in script
        assert "opscat-p176-live-" in script
        assert "forbidden_projects" in script
        assert "set -euo pipefail" in script
        assert "--auto-approve" not in script
    assert "APPLY_REVIEWED_PLAN" in deploy
    assert "EXPECTED_PLAN_SHA256" in deploy
    assert "p176-live.tfplan.json" in deploy
    assert ".variables.project_id.value == $project" in deploy
    assert ".variables.billing_account_id.value == $billing_account" in deploy
    assert "verify_saved_plan" in deploy
    assert 'select(.type == "google_project"' in apply_guard
    assert 'or .type == "google_billing_budget"' in apply_guard
    assert 'or .type == "google_monitoring_notification_channel"' in apply_guard
    assert 'google_compute_router_nat' in apply_guard
    assert 'bounded_web_dns_egress' in apply_guard
    assert 'deny_other_egress' in apply_guard
    assert 'verify-apply-plan.jq' in deploy
    assert "terraform -chdir=\"${SCRIPT_DIR}\" apply \"p176-live.tfplan\"" in deploy
    assert "APPLY_REVIEWED_DESTROY" in destroy
    assert "EXPECTED_PLAN_SHA256" in destroy
    assert "p176-live-destroy.tfplan.json" in destroy
    assert "command -v jq" in destroy
    assert "verify_destroy_plan" in destroy
    assert '"google_compute_router", "google_compute_router_nat"' in destroy_guard
    assert 'type == "google_project"' in destroy_guard
    assert 'verify-destroy-plan.jq' in destroy
    assert "terraform -chdir=\"${SCRIPT_DIR}\" apply \"p176-live-destroy.tfplan\"" in destroy


def test_p176_live_reviewed_preflight_is_plan_only_and_fail_closed() -> None:
    preflight = _read(INFRA / "preflight.sh")
    template = _read(INFRA / "terraform.tfvars.template")
    docs = _read(ROOT / "docs" / "tickets" / "p176" / "live-lab" / "reviewed-preflight.md")

    assert 'billing_account_id = "<gcp-billing-account-id>"' in template
    assert 'project_id         = "opscat-p176-live-<fresh-suffix>"' in template
    assert "project_number" not in template
    assert "budget_amount_krw" not in template
    assert "EXPECTED_PROJECT_NUMBER" not in preflight
    assert "EXPECTED_BILLING_ACCOUNT_ID=\"${EXPECTED_BILLING_ACCOUNT_ID:-}\"" in preflight
    assert "missing_expected_project_number" not in preflight
    assert "missing_expected_billing_account_id" in preflight
    assert "blocked_external_gate" in preflight
    assert "mutation_count: 0" in preflight
    assert "apply_attempted: false" in preflight
    assert "destroy_attempted: false" in preflight
    assert "P176_PREFLIGHT_RUN_PLAN" in preflight
    assert "verify-apply-plan.jq" in preflight
    assert ".variables.project_id.value == $project" in preflight
    assert "mktemp -d" in preflight
    assert "redacted_receipt" in preflight
    assert "generated_artifact_sensitive_content_detected" in preflight
    assert "possible_persisted_gcloud_credential_or_account_content" in preflight
    assert "active_gcloud_account" not in preflight
    assert "terraform.tfvars.template" in docs
    assert "must not run" in docs
    assert "`terraform apply`" in docs
    assert "`terraform destroy`" in docs
    assert "enable APIs" in docs
    assert "create projects" in docs
    assert "persist raw `gcloud` payloads" in docs
    assert 'terraform -chdir="${SCRIPT_DIR}" apply' not in preflight
    assert 'terraform -chdir="${SCRIPT_DIR}" destroy' not in preflight
    assert "services enable" not in preflight
    assert "projects create" not in preflight


def test_p176_live_preflight_writes_machine_readable_boundary_without_plan(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "terraform",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == -chdir=* ]]; then shift; fi
case "${1:-}" in
  version) echo "Terraform v1.15.1" ;;
  fmt) exit 0 ;;
  validate) echo "Success! The configuration is valid." ;;
  plan) echo "plan should not run in default preflight" >&2; exit 99 ;;
  *) echo "unexpected terraform command: $*" >&2; exit 98 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "gcloud",
        f"""#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "--version")
    echo "Google Cloud SDK 566.0.0"
    ;;
  "config list --format=json")
    echo '{{"core":{{"account":"{OWNER_EMAIL}","project":"prod-forbidden-project"}}}}'
    ;;
  "auth list --filter=status:ACTIVE --format=json")
    echo '[{{"account":"{OWNER_EMAIL}","status":"ACTIVE"}}]'
    ;;
  "billing accounts list --format=json")
    echo '[{{"name":"billingAccounts/{BILLING_ACCOUNT_ID}","open":true}}]'
    ;;
  *)
    echo "unexpected gcloud command: $*" >&2
    exit 97
    ;;
esac
""",
    )

    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["ARTIFACT_DIR"] = str(artifact_dir)
    env["TFVARS_FILE"] = str(tmp_path / "missing.tfvars")
    env["EXPECTED_PROJECT_ID"] = "opscat-p176-live-" + "test01"
    env["EXPECTED_BILLING_ACCOUNT_ID"] = BILLING_ACCOUNT_ID
    env["HOME"] = str(tmp_path)

    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    readiness = json.loads((artifact_dir / "p176-live-preflight-readiness.json").read_text())
    boundary = json.loads((artifact_dir / "p176-live-preflight-boundary.json").read_text())
    receipts = json.loads((artifact_dir / "p176-live-preflight-receipts.json").read_text())
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in artifact_dir.iterdir() if path.is_file())
    assert readiness["status"] == "blocked_external_gate"
    assert "missing_tfvars" in readiness["blocking_reasons"]
    assert "gcloud_active_project_forbidden" in readiness["blocking_reasons"]
    assert readiness["mutation_count"] == 0
    assert readiness["apply_attempted"] is False
    assert readiness["destroy_attempted"] is False
    assert readiness["active_gcloud_project_status"] == "forbidden"
    assert "active_gcloud_account" not in readiness
    assert "active_gcloud_project" not in readiness
    assert "stdout_path" not in json.dumps(readiness)
    assert "stderr_path" not in json.dumps(readiness)
    assert OWNER_EMAIL not in artifact_text
    assert ("opscat-p176-live-" + "test01") not in artifact_text
    assert f"billingAccounts/{BILLING_ACCOUNT_ID}" not in artifact_text
    assert boundary["status"] == "blocked_external_gate"
    assert boundary["boundary"] == "real Terraform plan not produced"
    assert boundary["mutation_count"] == 0
    assert receipts["receipts"]["blocked_boundary"]["sha256"]
    assert receipts["receipts"]["reviewed_plan"] is None


def test_p176_live_preflight_scans_gcloud_config_content_for_credentials(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    gcloud_config = tmp_path / ".config" / "gcloud"
    gcloud_config.mkdir(parents=True)
    (gcloud_config / "legacy.json").write_text(
        f'{{"client_email":"{PERSISTED_ADMIN_EMAIL}","private_key_id":"abc123"}}',
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["ARTIFACT_DIR"] = str(artifact_dir)
    env["TFVARS_FILE"] = str(tmp_path / "missing.tfvars")
    env["EXPECTED_PROJECT_ID"] = "opscat-p176-live-" + "test01"
    env["HOME"] = str(tmp_path)

    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    readiness = json.loads((artifact_dir / "p176-live-preflight-readiness.json").read_text())
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in artifact_dir.iterdir() if path.is_file())
    assert "possible_persisted_gcloud_credential_or_account_content" in readiness["blocking_reasons"]
    assert PERSISTED_ADMIN_EMAIL not in artifact_text
    assert "private_key_id" not in artifact_text


def test_p176_live_preflight_allows_secure_gcloud_metadata_and_nested_authorized_adc(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    gcloud_config = tmp_path / ".config" / "gcloud"
    legacy_dir = gcloud_config / "legacy" / "application_default_credentials"
    configurations = gcloud_config / "configurations"
    legacy_dir.mkdir(parents=True)
    configurations.mkdir(parents=True)
    for name in ("credentials.db", "access_tokens.db"):
        path = gcloud_config / name
        path.write_text("sqlite placeholder", encoding="utf-8")
        path.chmod(0o600)
    (legacy_dir / "adc.json").write_text(
        '{"type":"authorized_user","client_id":"placeholder.apps.googleusercontent.com","token_uri":"https://oauth2.googleapis.com/token"}',
        encoding="utf-8",
    )
    (legacy_dir / "adc.json").chmod(0o600)
    for path in (
        gcloud_config / "active_config",
        gcloud_config / ".last_update_check",
        gcloud_config / ".last_update_check.json",
        configurations / "config_default",
    ):
        path.write_text("default", encoding="utf-8")
        path.chmod(0o644)

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "unsafe_gcloud_credential_store_permissions" not in blocking_reasons
    assert "possible_persisted_gcloud_credential_or_account_content" not in blocking_reasons
    assert "possible_persisted_service_account_key_filename" not in blocking_reasons
    assert "unsafe_gcloud_adc_service_account_key_material" not in blocking_reasons


def test_p176_live_preflight_rejects_nested_service_account_adc_json(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    nested_adc = (
        tmp_path
        / ".config"
        / "gcloud"
        / "legacy"
        / "application_default_credentials"
        / "application_default_credentials.json"
    )
    nested_adc.parent.mkdir(parents=True)
    nested_adc.write_text(
        '{"type":"service_account","private_key":"-----BEGIN PRIVATE KEY-----\\nredacted\\n-----END PRIVATE KEY-----\\n"}',
        encoding="utf-8",
    )
    nested_adc.chmod(0o600)

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "unsafe_gcloud_adc_service_account_key_material" in blocking_reasons


def test_p176_live_preflight_does_not_treat_source_field_names_as_secrets(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    source_path = tmp_path / ".config" / "gcloud" / "sdk" / "example.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        'FIELDS = ["token_uri", "access_token", "refresh_token", "client_secret"]\n',
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "possible_persisted_gcloud_credential_or_account_content" not in blocking_reasons


def test_p176_live_preflight_allows_bundled_sdk_private_key_literal_source(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    bundled_source = (
        tmp_path
        / ".config"
        / "gcloud"
        / "platform"
        / "bundledpythonunix"
        / "virtenv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "google"
        / "auth"
        / "transport"
        / "__pycache__"
        / "ssh.py"
    )
    bundled_source.parent.mkdir(parents=True)
    bundled_source.write_text(
        'SAMPLE_KEY_HEADER = "-----BEGIN PRIVATE KEY-----"\n',
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "possible_persisted_gcloud_credential_or_account_content" not in blocking_reasons


def test_p176_live_preflight_allows_root_virtenv_private_key_literal_source(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    bundled_source = (
        tmp_path
        / ".config"
        / "gcloud"
        / "virtenv"
        / "lib"
        / "python3.13"
        / "site-packages"
        / "cryptography"
        / "hazmat"
        / "primitives"
        / "serialization"
        / "ssh.py"
    )
    bundled_source.parent.mkdir(parents=True)
    bundled_source.write_text(
        'SAMPLE_KEY_HEADER = "-----BEGIN PRIVATE KEY-----"\n',
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "possible_persisted_gcloud_credential_or_account_content" not in blocking_reasons


def test_p176_live_preflight_rejects_gcloud_log_with_oauth_token(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    log_path = tmp_path / ".config" / "gcloud" / "logs" / "2026.07.19" / "gcloud.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "refresh response access_token=ya29.syntheticTokenForRegression12345\n",
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "possible_persisted_gcloud_credential_or_account_content" in blocking_reasons


def test_p176_live_preflight_rejects_unexpected_json_with_token_secret(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    token_path = tmp_path / ".config" / "gcloud" / "unexpected.json"
    token_path.parent.mkdir(parents=True)
    token_path.write_text('{"refresh_token":"redacted-placeholder"}', encoding="utf-8")

    artifact_dir = tmp_path / "artifacts"
    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    blocking_reasons = json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]
    assert "possible_persisted_gcloud_credential_or_account_content" in blocking_reasons


def test_p176_live_preflight_rejects_symlink_artifact_directory(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    target_dir = tmp_path / "real-artifacts"
    target_dir.mkdir()
    artifact_dir = tmp_path / "artifact-link"
    artifact_dir.symlink_to(target_dir, target_is_directory=True)

    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70
    assert "symlink artifact directory" in result.stderr
    assert list(target_dir.iterdir()) == []


def test_p176_live_preflight_rejects_symlink_output_target(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    outside_target = tmp_path / "outside-readiness.json"
    (artifact_dir / "p176-live-preflight-readiness.json").symlink_to(outside_target)

    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70
    assert "symlink artifact output target" in result.stderr
    assert not outside_target.exists()


def test_p176_live_preflight_removes_stale_raw_provider_outputs(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_preflight_fake_tools(fake_bin)

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    stale_names = {
        "gcloud-config.stdout.json",
        "gcloud-auth-active.stdout.json",
        "gcloud-billing-accounts.stdout.json",
        "gcloud-key-filename-scan.txt",
        "terraform-version.stdout.txt",
    }
    for name in stale_names:
        (artifact_dir / name).write_text(f"{OWNER_EMAIL}\n", encoding="utf-8")

    env = _preflight_env(tmp_path, fake_bin, artifact_dir)
    result = subprocess.run(
        [str(INFRA / "preflight.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 2
    remaining_names = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    assert stale_names.isdisjoint(remaining_names)
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in artifact_dir.iterdir() if path.is_file())
    assert OWNER_EMAIL not in artifact_text
    assert "generated_artifact_sensitive_content_detected" not in json.loads(
        (artifact_dir / "p176-live-preflight-readiness.json").read_text()
    )["blocking_reasons"]


def test_apply_plan_guard_accepts_only_the_frozen_private_topology() -> None:
    assert _run_jq_guard("verify-apply-plan.jq", _valid_apply_plan()).returncode == 0


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong_project",
        "public_interface",
        "static_address",
        "broad_nat",
        "foreign_nat_subnet",
        "public_ingress",
        "extra_egress",
    ),
)
def test_apply_plan_guard_rejects_unsafe_plan_shapes(mutation: str) -> None:
    plan = _valid_apply_plan()
    if mutation == "wrong_project":
        plan["resource_changes"][1]["change"]["after"]["project"] = "prod-forbidden-project"
    elif mutation == "public_interface":
        plan["resource_changes"].append(
            _change(
                "google_compute_instance",
                "target",
                {"project": PROJECT_ID, "network_interface": [{"access_config": [{}]}]},
            )
        )
    elif mutation == "static_address":
        plan["resource_changes"].append(_change("google_compute_address", "nat", {"project": PROJECT_ID}))
    elif mutation == "broad_nat":
        plan["resource_changes"][1]["change"]["after"]["source_subnetwork_ip_ranges_to_nat"] = "ALL_SUBNETWORKS_ALL_IP_RANGES"
    elif mutation == "foreign_nat_subnet":
        plan["resource_changes"][1]["change"]["after"]["subnetwork"].append(
            {"name": "foreign-subnet", "source_ip_ranges_to_nat": ["ALL_IP_RANGES"]}
        )
    elif mutation == "public_ingress":
        plan["resource_changes"].append(
            _change(
                "google_compute_firewall",
                "public_http",
                {
                    "project": PROJECT_ID,
                    "name": "public-http",
                    "direction": "INGRESS",
                    "priority": 900,
                    "source_ranges": ["0.0.0.0/0"],
                    "source_tags": [],
                    "target_tags": ["opscat-p176-live-target"],
                    "allow": [{"protocol": "tcp", "ports": ["80"]}],
                    "deny": [],
                },
            )
        )
    else:
        plan["resource_changes"].append(
            _change(
                "google_compute_firewall",
                "unexpected_egress",
                {
                    "project": PROJECT_ID,
                    "name": "unexpected-egress",
                    "direction": "EGRESS",
                    "priority": 900,
                    "destination_ranges": ["0.0.0.0/0"],
                    "target_tags": ["opscat-p176-live-target"],
                    "allow": [{"protocol": "all", "ports": []}],
                    "deny": [],
                },
            )
        )
    assert _run_jq_guard("verify-apply-plan.jq", plan).returncode != 0


def test_destroy_plan_guard_accepts_delete_only_and_rejects_create_or_foreign_resources() -> None:
    valid = _valid_destroy_plan()
    assert _run_jq_guard("verify-destroy-plan.jq", valid, destroy=True).returncode == 0

    creates = deepcopy(valid)
    creates["resource_changes"][0]["change"]["actions"] = ["create"]
    assert _run_jq_guard("verify-destroy-plan.jq", creates, destroy=True).returncode != 0

    foreign = deepcopy(valid)
    foreign["resource_changes"][0]["change"]["before"]["project"] = "prod-forbidden-project"
    assert _run_jq_guard("verify-destroy-plan.jq", foreign, destroy=True).returncode != 0


PROJECT_ID = "opscat-p176-live-" + "test01"
BILLING_ACCOUNT_ID = "-".join(("000000", "000000", "000000"))


def _change(resource_type: str, name: str, after: dict[str, Any]) -> dict[str, Any]:
    return {
        "address": f"{resource_type}.{name}",
        "type": resource_type,
        "name": name,
        "change": {"actions": ["create"], "before": None, "after": after},
    }


def _valid_apply_plan() -> dict[str, Any]:
    tags = ["opscat-p176-live-target", "opscat-p176-live-observer"]
    return {
        "variables": {
            "project_id": {"value": PROJECT_ID},
            "billing_account_id": {"value": BILLING_ACCOUNT_ID},
            "cost_cutoff_budget_topic_name": {
                "value": "projects/opscat-p176-admin-test01/topics/p176-cost-cutoff-budget"
            },
        },
        "resource_changes": [
            _change(
                "google_compute_router",
                "p176_live",
                {"project": PROJECT_ID, "name": "p176-live-router", "region": "asia-northeast3"},
            ),
            _change(
                "google_compute_router_nat",
                "p176_live",
                {
                    "project": PROJECT_ID,
                    "name": "p176-live-nat",
                    "nat_ip_allocate_option": "AUTO_ONLY",
                    "source_subnetwork_ip_ranges_to_nat": "LIST_OF_SUBNETWORKS",
                    "subnetwork": [
                        {"name": "p176-live-subnet", "source_ip_ranges_to_nat": ["ALL_IP_RANGES"]}
                    ],
                },
            ),
            _change(
                "google_compute_firewall",
                "iap_ssh",
                {
                    "project": PROJECT_ID,
                    "name": "p176-live-iap-ssh",
                    "direction": "INGRESS",
                    "priority": 1000,
                    "source_ranges": ["35.235.240.0/20"],
                    "source_tags": [],
                    "target_tags": tags,
                    "allow": [{"protocol": "tcp", "ports": ["22"]}],
                    "deny": [],
                },
            ),
            _change(
                "google_compute_firewall",
                "observer_to_target_private",
                {
                    "project": PROJECT_ID,
                    "name": "p176-live-observer-to-target-private",
                    "direction": "INGRESS",
                    "priority": 1000,
                    "source_ranges": [],
                    "source_tags": ["opscat-p176-live-observer"],
                    "target_tags": ["opscat-p176-live-target"],
                    "allow": [{"protocol": "tcp", "ports": ["8000"]}],
                    "deny": [],
                },
            ),
            _change(
                "google_compute_firewall",
                "observer_to_target_private_egress",
                {
                    "project": PROJECT_ID,
                    "name": "p176-live-observer-to-target-private-egress",
                    "direction": "EGRESS",
                    "priority": 900,
                    "destination_ranges": ["10.176.0.10/32"],
                    "target_tags": ["opscat-p176-live-observer"],
                    "allow": [{"protocol": "tcp", "ports": ["8000"]}],
                    "deny": [],
                },
            ),
            _change(
                "google_compute_firewall",
                "bounded_web_dns_egress",
                {
                    "project": PROJECT_ID,
                    "name": "p176-live-bounded-web-dns-egress",
                    "direction": "EGRESS",
                    "priority": 1000,
                    "destination_ranges": ["0.0.0.0/0"],
                    "target_tags": tags,
                    "allow": [
                        {"protocol": "tcp", "ports": ["53", "80", "443"]},
                        {"protocol": "udp", "ports": ["53"]},
                    ],
                    "deny": [],
                },
            ),
            _change(
                "google_compute_firewall",
                "deny_other_egress",
                {
                    "project": PROJECT_ID,
                    "name": "p176-live-deny-other-egress",
                    "direction": "EGRESS",
                    "priority": 1100,
                    "destination_ranges": ["0.0.0.0/0"],
                    "target_tags": tags,
                    "allow": [],
                    "deny": [{"protocol": "all", "ports": []}],
                },
            ),
        ],
        "prior_state": {"values": {"root_module": {"resources": []}}},
    }


def _valid_destroy_plan() -> dict[str, Any]:
    def deleting(resource_type: str, name: str, before: dict[str, Any]) -> dict[str, Any]:
        return {
            "address": f"{resource_type}.{name}",
            "type": resource_type,
            "name": name,
            "change": {"actions": ["delete"], "before": before, "after": None},
        }

    return {
        "resource_changes": [
            deleting(
                "google_compute_firewall",
                "deny_other_egress",
                {"project": PROJECT_ID, "name": "p176-live-deny-other-egress"},
            ),
        ],
        "variables": {
            "project_id": {"value": PROJECT_ID},
        },
    }


def _run_jq_guard(name: str, plan: dict[str, Any], *, destroy: bool = False) -> subprocess.CompletedProcess[str]:
    command = ["jq", "-e", "--arg", "project", PROJECT_ID]
    if destroy:
        command.extend(["--arg", "billing_account", BILLING_ACCOUNT_ID])
    command.extend(["-f", str(INFRA / name)])
    return subprocess.run(command, input=json.dumps(plan), text=True, capture_output=True, check=False)


def _write_preflight_fake_tools(fake_bin: Path) -> None:
    _write_executable(
        fake_bin / "terraform",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == -chdir=* ]]; then shift; fi
case "${1:-}" in
  version) echo "Terraform v1.15.1" ;;
  fmt) exit 0 ;;
  validate) echo "Success! The configuration is valid." ;;
  plan) echo "plan should not run in default preflight" >&2; exit 99 ;;
  *) echo "unexpected terraform command: $*" >&2; exit 98 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "gcloud",
        f"""#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "--version")
    echo "Google Cloud SDK 566.0.0"
    ;;
  "config list --format=json")
    echo '{{"core":{{"account":"{OWNER_EMAIL}","project":"opscat-p176-admin"}}}}'
    ;;
  "auth list --filter=status:ACTIVE --format=json")
    echo '[{{"account":"{OWNER_EMAIL}","status":"ACTIVE"}}]'
    ;;
  "billing accounts list --format=json")
    echo '[{{"name":"billingAccounts/{BILLING_ACCOUNT_ID}","open":true}}]'
    ;;
  *)
    echo "unexpected gcloud command: $*" >&2
    exit 97
    ;;
esac
""",
    )


def _preflight_env(tmp_path: Path, fake_bin: Path, artifact_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["ARTIFACT_DIR"] = str(artifact_dir)
    env["TFVARS_FILE"] = str(tmp_path / "missing.tfvars")
    env["EXPECTED_PROJECT_ID"] = PROJECT_ID
    env["EXPECTED_BILLING_ACCOUNT_ID"] = BILLING_ACCOUNT_ID
    env["HOME"] = str(tmp_path)
    return env


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
