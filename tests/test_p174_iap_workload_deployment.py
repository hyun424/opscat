from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "gcp" / "p174"
LAB = ROOT / "lab" / "p174"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_p174_iap_workload_scripts_are_bash_syntax_valid() -> None:
    for script in ("workload-iap.sh", "observer-host-evidence-collector.sh"):
        result = subprocess.run(["bash", "-n", str(INFRA / script)], check=False, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def _deployment_plan(*, include_bundle_path: bool = True) -> str:
    lines = [
        "PLAN_KIND=workload-deploy",
        "CREATED_AT=20260717T120000Z",
        "PROJECT_ID=opscat-p174-sample-lab",
        "ZONE=asia-northeast3-a",
        "TARGET_VM=p174-target",
        "OBSERVER_VM=p174-observer",
        "TARGET_BIND_IP=10.174.0.10",
        "OBSERVER_BIND_IP=10.174.0.20",
    ]
    if include_bundle_path:
        lines.append("BUNDLE_PATH=/reviewed/bundle.tgz")
    lines.extend(
        [
            "BUNDLE_SHA256=" + "a" * 64,
            "BUNDLE_MANIFEST_SHA256=" + "b" * 64,
            "HOST_COLLECTOR_SHA256=" + "c" * 64,
            "REMOTE_BASE=/opt/opscat/p174",
        ]
    )
    return "\n".join(lines) + "\n"


def test_p174_plan_parser_accepts_numeric_keys_and_overrides_inherited_values(tmp_path: Path) -> None:
    plan = tmp_path / "plan.env"
    plan.write_text(_deployment_plan(), encoding="utf-8")
    env = os.environ | {
        "EXPECTED_PROJECT_ID": "opscat-p174-sample-lab",
        "BUNDLE_PATH": "/unreviewed/inherited.tgz",
    }
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; load_plan "$2"; printf "%s\\n" "$BUNDLE_PATH"',
            "bash",
            str(INFRA / "workload-iap.sh"),
            str(plan),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "/reviewed/bundle.tgz\n"


def test_p174_plan_parser_rejects_missing_bundle_path_despite_inherited_value(tmp_path: Path) -> None:
    plan = tmp_path / "plan.env"
    plan.write_text(_deployment_plan(include_bundle_path=False), encoding="utf-8")
    env = os.environ | {
        "EXPECTED_PROJECT_ID": "opscat-p174-sample-lab",
        "BUNDLE_PATH": "/unreviewed/inherited.tgz",
    }
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; load_plan "$2"',
            "bash",
            str(INFRA / "workload-iap.sh"),
            str(plan),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "missing BUNDLE_PATH" in result.stderr


def test_p174_runtime_writer_emits_strict_authority_file(tmp_path: Path) -> None:
    plan = tmp_path / "plan.env"
    plan.write_text(_deployment_plan(), encoding="utf-8")
    runtime = tmp_path / "runtime"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; load_plan "$2"; write_runtime_envs "$3" "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" "ffffffffffffffffffffffffffffffff"',
            "bash",
            str(INFRA / "workload-iap.sh"),
            str(plan),
            str(runtime),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"EXPECTED_PROJECT_ID": "opscat-p174-sample-lab"},
    )

    assert result.returncode == 0, result.stderr
    authority = dict(line.split("=", 1) for line in (runtime / "authority.env").read_text(encoding="utf-8").splitlines())
    assert set(authority) == {
        "P174_ACTION_CAPABILITY",
        "P174_FAULT_CAPABILITY",
        "P174_PROJECT_ID",
        "P174_TARGET_ID",
        "P174_RUN_ID",
        "P174_POLICY_VERSION",
    }
    assert authority["P174_POLICY_VERSION"] == "p174-policy-v1"
    assert "P174_TARGET_BIND_IP" in (runtime / "target.env").read_text(encoding="utf-8")
    assert (runtime / "authority.env").stat().st_mode & 0o777 == 0o600


def test_p174_workload_iap_deployment_has_plan_apply_and_exact_vm_allowlists() -> None:
    script = _read(INFRA / "workload-iap.sh")

    assert 'ALLOWED_ZONE="asia-northeast3-a"' in script
    assert 'TARGET_INSTANCE="p174-target"' in script
    assert 'OBSERVER_INSTANCE="p174-observer"' in script
    assert 'TARGET_PRIVATE_IP="10.174.0.10"' in script
    assert 'OBSERVER_PRIVATE_IP="10.174.0.20"' in script
    assert "EXPECTED_PROJECT_ID" in script
    assert "opscat-p174-" in script
    assert "P174_FORBIDDEN_PROJECT_IDS" in script
    assert "forbidden_projects" in script

    assert "PLAN_KIND=workload-deploy" in script
    assert "PLAN_KIND=workload-teardown" in script
    assert "EXPECTED_PLAN_SHA256" in script
    assert "APPLY_REVIEWED_WORKLOAD=1" in script
    assert "APPLY_REVIEWED_WORKLOAD_TEARDOWN=1" in script
    assert "validate_plan_digest" in script
    assert "action-input-$(timestamp)-${request_id}" in script
    assert '--evidence-hash "${evidence_hash}"' in script
    assert '--pool-size "${pool_size}"' in script
    assert "observer receipt chain is empty" in script
    assert "observer evaluation history is empty" in script
    assert "host compute evidence does not prove the reviewed running target" in script
    assert ".project_id == $project" in script
    assert ".self_link_project == $project" in script
    assert 'ALLOW_UNHEALTHY_EVIDENCE=1 PROJECT_ID="${plan_project}" collect_evidence' in script
    assert 'ALLOW_UNHEALTHY_EVIDENCE=1 EVIDENCE_DIR="${action_evidence_dir}" collect_evidence' in script
    assert '[[ "${collect_health}" != "true"' in script
    assert '(.evaluation.failures | sort) == ["health_signal_failed:api"]' in script
    assert "observer evidence is not a safely observed API incident" in script
    assert 'source "${plan_file}"' not in script
    assert "invalid plan line" in script
    assert "unset PLAN_KIND CREATED_AT PROJECT_ID" in script
    assert "duplicate plan key" in script
    assert "BUNDLE_PATH:?missing BUNDLE_PATH in workload deployment plan" in script
    assert "HOST_COLLECTOR_SHA256:?missing HOST_COLLECTOR_SHA256 in workload deployment plan" in script
    assert "--exclude='./runtime'" in script
    assert "--exclude='*/__pycache__'" in script
    assert "--exclude='*.pyc'" in script
    assert "printf -v cleanup_cmd 'rm -rf -- %q'" in script
    assert "trap '${runtime_dir}'" not in script
    assert "trap 'rm -rf \"${runtime_dir}\"' EXIT" not in script
    assert 'rm -rf "${work_dir}"' not in script
    assert "/tmp/opscat-p174-workload-*" in script
    assert "terraform apply" not in script
    assert "terraform destroy" not in script
    assert "--auto-approve" not in script
    install_section = script.index("install_observer_host_collector()")
    rotate_section = script.index("compute-target-evidence-predeploy-", install_section)
    stop_section = script.index("sudo systemctl stop", install_section)
    assert stop_section < rotate_section
    assert "systemctl show --property=ActiveState --value" in script[stop_section:rotate_section]
    assert "collector unit not inactive" in script[stop_section:rotate_section]
    assert "systemctl show --property=LoadState --value" in script[install_section:stop_section]
    assert "load_state" in script[install_section:stop_section]
    assert "== not-found" in script[install_section:stop_section]
    snapshot_section = script.index("host-compute-evidence.tgz")
    assert "collector_timer_was_active=0" in script[:snapshot_section]
    assert "collector service not inactive during evidence snapshot" in script[:snapshot_section]
    assert "unexpected collector timer state" in script[:snapshot_section]
    assert "unexpected collector service state" in script[:snapshot_section]
    assert "trap restore_collector_timer EXIT" in script[:snapshot_section]
    trap_section = script.index("trap restore_collector_timer EXIT")
    snapshot_stop = script.index("sudo systemctl stop opscat-p174-observer-evidence.timer", trap_section)
    assert trap_section < snapshot_stop < snapshot_section


def test_p174_workload_iap_uses_iap_only_and_generates_uncommitted_capability() -> None:
    script = _read(INFRA / "workload-iap.sh")
    target_compose = _read(LAB / "docker-compose.target.yml")

    assert "gcloud compute ssh" in script
    assert "gcloud compute scp" in script
    assert "--tunnel-through-iap" in script
    assert "gcloud compute start-iap-tunnel" not in script
    assert 'sock.bind(("127.0.0.1", 0))' in script
    assert '-L "127.0.0.1:${local_port}:${TARGET_BIND_IP}:8020"' in script
    assert "ExitOnForwardFailure=yes" in script
    assert 'kill -0 "${tunnel_pid}"' in script
    assert "openssl rand -hex 32" in script
    assert "P174_ACTION_CAPABILITY=" in script
    assert "P174_FAULT_CAPABILITY=" in script
    assert "missing separated runtime capabilities" in script
    assert '"${action_capability}" != "${fault_capability}"' in script
    assert "P174_FAULT_CAPABILITY: ${P174_FAULT_CAPABILITY" in target_compose
    assert "lab/p174/.env" not in script
    assert "BEGIN PRIVATE KEY" not in script
    assert "gcloud auth activate-service-account" not in script


def test_p175_live_iap_harness_is_reviewed_bound_and_loopback_only() -> None:
    script = _read(INFRA / "workload-iap.sh")
    observer_compose = _read(LAB / "docker-compose.observer.yml")

    assert "workload-iap.sh p175-plan" in script
    assert "workload-iap.sh p175-live" in script
    assert "P175_REVIEWED_HARNESS=1" in script
    assert "P175_REVIEWER_ID" in script
    assert "EXPECTED_P175_PLAN_SHA256" in script
    assert "EXPECTED_HARNESS_MANIFEST_SHA256" in script
    assert "PLAN_KIND=p175-live-harness" in script
    assert "WORKLOAD_PLAN_SHA256=${expected}" in script
    assert "HARNESS_MANIFEST_SHA256=${harness_sha}" in script
    assert "PROVIDER_MANIFEST_SHA256=${provider_sha}" in script
    assert 'ORCHESTRATOR_SHA256=$(sha256_file "${BASH_SOURCE[0]}")' in script
    assert "ACTION_CAPABILITY_SHA256=$(printf '%s' \"${action_capability}\" | shasum -a 256" in script
    assert "FAULT_CAPABILITY_SHA256=$(printf '%s' \"${fault_capability}\" | shasum -a 256" in script
    assert 'validate_plan_digest "${p175_plan}" "${expected}"' in script
    assert 'validate_plan_digest "${WORKLOAD_PLAN_FILE}" "${WORKLOAD_PLAN_SHA256}"' in script
    assert '[[ "$(sha256_file "${HARNESS_MANIFEST_PATH}")" == "${HARNESS_MANIFEST_SHA256}" ]]' in script
    assert '[[ "$(sha256_file "${PROVIDER_MANIFEST_PATH}")" == "${PROVIDER_MANIFEST_SHA256}" ]]' in script
    assert '[[ "$(sha256_file "${BASH_SOURCE[0]}")" == "${ORCHESTRATOR_SHA256}" ]]' in script
    assert '[[ "${expected_harness}" == "${HARNESS_MANIFEST_SHA256}" ]]' in script
    assert 'P174_POLICY_VERSION)" == "p174-policy-v1"' in script
    assert '"${run_id}" == "p174-live-${BUNDLE_SHA256:0:16}"' in script

    assert '"127.0.0.1:8030:8030"' in observer_compose
    assert 'ports:' in observer_compose
    assert '0.0.0.0:8030' not in observer_compose
    assert '-L "127.0.0.1:${local_port}:${remote_host}:${remote_port}"' in script
    assert 'start_iap_loopback_tunnel "${TARGET_VM}" "${target_local_port}" "${TARGET_BIND_IP}"' in script
    assert 'start_iap_loopback_tunnel "${OBSERVER_VM}" "${observer_local_port}" "127.0.0.1"' in script
    assert "TARGET_LOOPBACK_PORT=8020" in script
    assert "OBSERVER_LOOPBACK_PORT=8030" in script
    assert '--observer-endpoint "http://127.0.0.1:${observer_local_port}"' in script
    assert '--action-endpoint "http://127.0.0.1:${target_local_port}"' in script
    assert "P175_ACTION_ENDPOINT" not in script
    assert "P175_OBSERVER_ENDPOINT" not in script
    assert "10.174.0.20:8030" not in script

    assert "validate_runtime_authority" in script
    assert '"${action_capability}" != "${fault_capability}"' in script
    assert '--authority-file "${ACTION_ENV_PATH}"' in script
    assert '--action-capability "${action_capability}"' not in script
    assert '--fault-capability "${fault_capability}"' not in script
    assert 'P174_ACTION_CAPABILITY="${fault_capability}"' not in script
    assert 'P174_FAULT_CAPABILITY="${action_capability}"' not in script
    assert "source \"${WORKLOAD_PLAN_FILE}\"" not in script
    assert "source \"${p175_plan}\"" not in script
    assert "load_p175_plan" in script
    assert "invalid P175 plan line" in script
    assert "unexpected P175 plan key" in script
    assert "duplicate P175 plan key" in script

    assert "scripts/run_p174_live_harness.py" in script
    assert "--allow-live-lab" in script
    assert "--provider-manifest" in script
    assert "--manifest" in script
    assert "--output-summary" in script
    assert "--output-jsonl" in script
    assert 'summary_tmp="${EVAL_DIR}/p175-live-summary.json.tmp"' in script
    assert 'jsonl_tmp="${EVAL_DIR}/p175-live-evidence.jsonl.tmp"' in script
    assert "max_args=(--max-scenarios 100)" in script
    assert 'mv -f "${summary_tmp}" "${summary_out}"' in script
    assert 'mv -f "${jsonl_tmp}" "${jsonl_out}"' in script
    assert '.qualified == true and .diagnostic_campaign_only == false and .status == "qualified"' in script
    assert 'kill %q %q 2>/dev/null || true; wait %q %q 2>/dev/null || true; rm -f -- %q %q' in script
    assert 'trap "${cleanup_cmd}" EXIT' in script
    assert script.index('trap "${cleanup_cmd}" EXIT', script.index('start_iap_loopback_tunnel "${TARGET_VM}"')) < script.index('start_iap_loopback_tunnel "${OBSERVER_VM}"')
    assert 'trap - EXIT' in script
    assert 'wait_loopback_ready "${target_pid}"' in script
    assert 'wait_loopback_ready "${observer_pid}"' in script
    assert "P175_DIAGNOSTIC_CAMPAIGN_ONLY" in script
    assert "--diagnostic-campaign-only" in script
    assert '${diagnostic_args[@]+"${diagnostic_args[@]}"}' in script
    assert '.status == "diagnostic_complete"' in script


def test_p174_observer_host_collector_is_host_only_bounded_and_token_safe() -> None:
    deploy = _read(INFRA / "workload-iap.sh")
    collector = _read(INFRA / "observer-host-evidence-collector.sh")

    assert "observer-host-evidence-collector.sh" in deploy
    assert "opscat-p174-observer-evidence.timer" in deploy
    assert "opscat-p174-container-metadata-block.service" in deploy
    assert "169.254.169.254/32 -j REJECT" in deploy
    assert "/var/lib/opscat-p174/evidence" in deploy
    assert "/var/lib/opscat-p174/evidence/history" in deploy
    assert "compute-target-evidence-predeploy-" in deploy
    assert "truncate -s 0 /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl" in deploy
    install_section = deploy.index("install_observer_host_collector()")
    collector_stop = deploy.index("sudo systemctl stop", install_section)
    assert collector_stop < deploy.index("compute-target-evidence-predeploy-", install_section)
    assert "collector unit not inactive" in deploy[collector_stop:]
    assert deploy.index("truncate -s 0 /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl") < deploy.index(
        "systemctl start opscat-p174-observer-evidence.service"
    )
    assert "host-compute-evidence.tgz" in deploy
    assert "fault-controller-state.json" in deploy

    assert "metadata.google.internal/computeMetadata/v1" in collector
    assert "https://compute.googleapis.com/compute/v1" in collector
    assert "/projects/${PROJECT_ID}/zones/${ZONE}/instances/${TARGET_INSTANCE}" in collector
    assert '[[ "${ZONE}" == "asia-northeast3-a" ]]' in collector
    assert '[[ "${TARGET_INSTANCE}" == "p174-target" ]]' in collector
    assert "access_token" in collector
    assert "unset token" in collector
    assert "resource_body_sha256" in collector
    assert "fingerprint_hash" in collector
    assert "label_fingerprint_hash" in collector
    assert "compute-target-evidence.jsonl" in collector
    assert '"project_id": project_id' in collector
    assert '"self_link_project": project_from_self_link' in collector
    assert "Authorization: Bearer" in collector
    assert "BEGIN PRIVATE KEY" not in collector
    assert "activate-service-account" not in collector


def test_p174_mutation_capabilities_are_only_in_fault_controller() -> None:
    compose = _read(LAB / "docker-compose.target.yml")
    before_controller, controller = compose.split("  fault-controller:\n", 1)
    controller, after_controller = controller.split("  loadgen:\n", 1)

    assert "P174_ACTION_CAPABILITY" not in before_controller
    assert "P174_FAULT_CAPABILITY" not in before_controller
    assert "P174_ACTION_CAPABILITY" in controller
    assert "P174_FAULT_CAPABILITY" in controller
    assert "P174_ACTION_CAPABILITY" not in after_controller
    assert "P174_FAULT_CAPABILITY" not in after_controller


def test_p174_workload_teardown_removes_runtime_authority_and_host_units() -> None:
    script = _read(INFRA / "workload-iap.sh")

    assert "disable --now opscat-p174-observer-evidence.timer" in script
    assert "disable --now opscat-p174-container-metadata-block.service" in script
    assert "rm -rf /usr/local/lib/opscat-p174 /etc/opscat-p174 '${REMOTE_BASE}' '${REMOTE_ARCHIVE}'" in script
    assert "rm -rf '${REMOTE_BASE}' '${REMOTE_ARCHIVE}'" in script
    assert '"${LAB_DIR}/runtime/${PROJECT_ID}.env"' in script
    assert '"${LAB_DIR}/runtime/${PROJECT_ID}-manifest.json"' in script
    assert "P174_FAULT_CAPABILITY" in script
    assert "P174_PURGE_REMOTE_EVIDENCE" in script
    assert "P174_EXPORTED_EVIDENCE_DIR" in script
    assert "sudo rm -rf /var/lib/opscat-p174" in script
