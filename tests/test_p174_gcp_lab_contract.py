from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "gcp" / "p174"
LAB = ROOT / "lab" / "p174"
FORBIDDEN_PROJECTS = {
    "forbidden-existing-project-a",
    "forbidden-existing-project-b",
    "forbidden-existing-project-c",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _copy_p174_script_with_stubbed_terraform(
    tmp_path: Path,
    script_name: str,
    tfvars: str | None,
) -> tuple[Path, Path, dict[str, str]]:
    workdir = tmp_path / script_name.removesuffix(".sh")
    workdir.mkdir()
    script = workdir / script_name
    shutil.copy2(INFRA / script_name, script)
    if tfvars is not None:
        (workdir / "terraform.tfvars").write_text(tfvars, encoding="utf-8")

    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    marker = tmp_path / f"{script_name}.terraform-called"
    (tools / "terraform").write_text(
        f"#!/usr/bin/env bash\nprintf called > {marker}\nexit 99\n",
        encoding="utf-8",
    )
    (tools / "date").write_text(
        "#!/usr/bin/env bash\nprintf '20260720\\n'\n",
        encoding="utf-8",
    )
    (tools / "terraform").chmod(0o755)
    (tools / "date").chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tools}{os.pathsep}{env['PATH']}"
    env["EXPECTED_PROJECT_ID"] = "opscat-p174-abcdef"
    env["EXPECTED_BILLING_ACCOUNT_ID"] = "000000-000000-000000"
    return script, marker, env


def _run_bash(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_p174_live_manifest_freezes_isolation_and_authority() -> None:
    path = ROOT / "evals" / "p174" / "input" / "live-session-manifest.example.json"
    payload = json.loads(_read(path))

    assert payload["schema_version"] == "p174.live_session_manifest.v1"
    assert payload["organization_id"] == "000000000000"
    assert payload["billing_account_id"] == "000000-000000-000000"
    assert payload["project_id"].startswith("opscat-p174-")
    assert payload["target_id"] == "p174-target"
    assert payload["run_id"].startswith("p174-live-")
    assert payload["zone"] == "asia-northeast3-a"
    assert set(payload["allowed_actions"]) == {"tune_pool", "restart_worker", "rollback_canary"}
    assert payload["allowed_targets"] == ["p174-target"]
    assert FORBIDDEN_PROJECTS <= set(payload["forbidden_project_ids"])
    assert payload["lease_ttl_seconds"] <= 300
    assert payload["deadman_seconds"] <= 120
    assert payload["kill_switch"] is False
    assert payload["dry_run"] is False
    assert payload["production_mutation_allowed"] is False
    assert payload["user_staging_mutation_allowed"] is False
    assert payload["service_account_keys_allowed"] is False
    assert payload["live_apply_acknowledged"] is False


def test_p174_terraform_isolated_project_budget_and_two_vm_contract() -> None:
    required = {
        "versions.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "target-startup.sh",
        "observer-startup.sh",
        "README.md",
    }
    assert required <= {path.name for path in INFRA.iterdir() if path.is_file()}

    terraform = "\n".join(_read(path) for path in INFRA.glob("*.tf"))
    assert "google_project" in terraform
    assert 'auto_create_network = false' in terraform
    assert 'deletion_policy     = "DELETE"' in terraform
    assert "billing_account     = var.billing_account_id" in terraform
    assert "google_billing_project_info" not in terraform
    assert "google_billing_budget" in terraform
    assert "250000" in terraform
    assert "var.budget_amount_krw > 0 && var.budget_amount_krw <= 250000" in terraform
    assert "e2-standard-8" in terraform
    assert "e2-standard-2" in terraform
    assert 'var.target_machine_type == "e2-standard-8"' in terraform
    assert 'var.observer_machine_type == "e2-standard-2"' in terraform
    assert 'purpose   = "opscat-lab"' in terraform
    assert 'owner     = "p174-lab"' in terraform
    assert 'expires_on = "20260801"' in terraform
    assert "google_compute_instance" in terraform
    assert "target" in terraform and "observer" in terraform
    assert "enable-oslogin" in terraform
    assert 'account_id   = "p174-target"' in terraform
    assert 'account_id   = "p174-observer"' in terraform
    assert 'account_id   = "p174-action"' not in terraform
    assert 'account_id   = "p174-fault"' not in terraform
    assert 'account_id   = "p174-evaluator"' not in terraform
    assert "google_project_iam_custom_role" not in terraform
    assert "roles/compute.viewer" in terraform
    assert "roles/logging.viewer" in terraform
    assert "roles/monitoring.viewer" in terraform
    assert "roles/owner" not in terraform
    assert "roles/editor" not in terraform
    assert "service_account_key" not in terraform
    assert "compute.instances.osAdminLogin" not in terraform
    assert 'name                    = "default"' not in terraform
    assert 'auto_create_subnetworks = true' not in terraform
    assert terraform.count("access_config") == 2
    for forbidden in FORBIDDEN_PROJECTS:
        assert forbidden not in terraform


def test_p174_firewall_has_no_public_application_or_opscat_ingress() -> None:
    terraform = "\n".join(_read(path) for path in INFRA.glob("*.tf"))
    assert "35.235.240.0/20" in terraform
    assert "iap" in terraform.lower()
    assert "source_tags" in terraform
    assert "opscat-observer" in terraform
    assert "opscat-target" in terraform
    assert 'source_ranges = ["0.0.0.0/0"]' not in terraform
    assert 'ports    = ["8000", "8020", "9090", "3100"]' in terraform
    assert '"5432"' not in terraform
    assert '"6379"' not in terraform


def test_p174_startup_scripts_only_bootstrap_host_runtime() -> None:
    for name in ("target-startup.sh", "observer-startup.sh"):
        script = _read(INFRA / name)
        assert script.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in script
        assert "docker" in script
        assert "DOCKER-USER" in script
        assert "169.254.169.254/32" in script
        assert "p174-block-container-metadata.service" in script
        assert "-I DOCKER-USER 1 -d 169.254.169.254/32 -j REJECT" in script
        assert "NVIDIA_API_KEY" not in script
        assert "BEGIN PRIVATE KEY" not in script
        assert "gcloud auth activate-service-account" not in script
        assert "p174-expiry-shutdown.timer" in script
        assert "OnCalendar=2026-08-01 00:00:00 UTC" in script


def test_p174_target_compose_has_real_workload_observability_and_limits() -> None:
    compose = _read(LAB / "docker-compose.target.yml")
    for service in (
        "api",
        "worker",
        "postgres",
        "redis",
        "prometheus",
        "loki",
        "promtail",
        "node-exporter",
        "cadvisor",
        "fault-controller",
        "loadgen",
    ):
        assert f"  {service}:" in compose
    assert "healthcheck:" in compose
    assert "restart: unless-stopped" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "mem_limit:" in compose
    assert "pids_limit:" in compose
    assert "cpus:" in compose
    assert 'P174_INITIAL_POOL_SIZE: "16"' in compose
    assert 'REQUEST_INTERVAL_SECONDS: "0.25"' in compose
    assert "OPSCAT_ACTION_CAPABILITY" not in compose
    assert "/var/run/docker.sock" not in compose


def test_p174_observer_compose_has_loopback_only_port_and_separates_evaluator() -> None:
    compose = _read(LAB / "docker-compose.observer.yml")
    assert "observer:" in compose
    assert "evaluator:" in compose
    assert "ports:" in compose
    assert '"127.0.0.1:8030:8030"' in compose
    assert '"0.0.0.0:8030:8030"' not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "mem_limit:" in compose
    assert "pids_limit:" in compose


def test_p174_retention_and_prometheus_scrape_are_bounded() -> None:
    prometheus = _read(LAB / "observability" / "prometheus.yml")
    loki = _read(LAB / "observability" / "loki.yml")
    compose = _read(LAB / "docker-compose.target.yml")
    assert "scrape_interval: 15s" in prometheus
    assert "--storage.tsdb.retention.time=48h" in compose
    assert "retention_period: 48h" in loki


def test_p174_deploy_and_destroy_scripts_verify_frozen_project() -> None:
    deploy = _read(INFRA / "deploy.sh")
    destroy = _read(INFRA / "destroy.sh")
    for script in (deploy, destroy):
        assert "EXPECTED_PROJECT_ID" in script
        assert "EXPECTED_BILLING_ACCOUNT_ID" in script
        assert "declared_billing_account" in script
        assert "billing_account_id" in script
        assert "forbidden" in script.lower()
        assert "set -euo pipefail" in script
        assert "does not match EXPECTED_BILLING_ACCOUNT_ID" in script
    assert "terraform plan" in deploy
    assert "terraform apply" in deploy
    assert "--arg billing_account" in deploy
    assert ".variables.billing_account_id.value == $billing_account" in deploy
    assert ".change.after.billing_account == $billing_account" in deploy
    assert "terraform destroy" in destroy
    assert "--auto-approve" not in destroy
    assert "APPLY_REVIEWED_PLAN" in deploy
    assert "EXPECTED_PLAN_SHA256" in deploy
    assert "APPLY_REVIEWED_DESTROY" in destroy
    assert "EXPECTED_PLAN_SHA256" in destroy
    assert "EXPIRY_DATE_UTC=\"20260801\"" in deploy
    assert "date -u +%Y%m%d" in deploy
    assert "p174-destroy.tfplan.json" in destroy
    assert "command -v jq" in destroy
    assert "--arg billing_account" in destroy
    assert ".variables.billing_account_id.value == $billing_account" in destroy
    assert '.type == "google_project"' in destroy
    assert '.name == "p174"' in destroy
    assert '.change.before.project_id == $project' in destroy
    assert "EXPECTED_BILLING_ACCOUNT_ID from local-only runtime configuration" in destroy
    assert ".change.before.billing_account == $billing_account" in destroy
    assert 'billingAccounts/" + $billing_account' not in destroy
    assert '.change.before.budget_filter[0].projects == [("projects/" + $project_number)]' in destroy
    assert '.change.actions == ["delete"]' in destroy
    assert 'has_action("create") or has_action("update")' in destroy
    assert 'terraform -chdir="${SCRIPT_DIR}" apply "p174-destroy.tfplan"' in destroy


def test_p174_deploy_and_destroy_require_expected_billing_before_terraform(tmp_path: Path) -> None:
    tfvars = (
        'project_id = "opscat-p174-abcdef"\n'
        'billing_account_id = "000000-000000-000000"\n'
    )
    for script_name in ("deploy.sh", "destroy.sh"):
        script, marker, env = _copy_p174_script_with_stubbed_terraform(tmp_path, script_name, tfvars)
        env.pop("EXPECTED_BILLING_ACCOUNT_ID")

        completed = _run_bash(script, env)

        assert completed.returncode != 0
        assert "EXPECTED_BILLING_ACCOUNT_ID" in completed.stderr
        assert not marker.exists()


def test_p174_deploy_and_destroy_reject_missing_tfvars_billing_before_terraform(tmp_path: Path) -> None:
    tfvars = 'project_id = "opscat-p174-abcdef"\n'
    for script_name in ("deploy.sh", "destroy.sh"):
        script, marker, env = _copy_p174_script_with_stubbed_terraform(tmp_path, script_name, tfvars)

        completed = _run_bash(script, env)

        assert completed.returncode != 0
        assert "billing_account_id <unset> does not match EXPECTED_BILLING_ACCOUNT_ID" in completed.stderr
        assert not marker.exists()


def test_p174_deploy_and_destroy_reject_mismatched_tfvars_billing_before_terraform(tmp_path: Path) -> None:
    tfvars = (
        'project_id = "opscat-p174-abcdef"\n'
        'billing_account_id = "111111-111111-111111"\n'
    )
    for script_name in ("deploy.sh", "destroy.sh"):
        script, marker, env = _copy_p174_script_with_stubbed_terraform(tmp_path, script_name, tfvars)

        completed = _run_bash(script, env)

        assert completed.returncode != 0
        assert "does not match EXPECTED_BILLING_ACCOUNT_ID" in completed.stderr
        assert not marker.exists()
