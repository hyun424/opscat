#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LIVE_LAB_DIR="${REPO_ROOT}/lab/p176/live"
OBSERVER_LAB_DIR="${REPO_ROOT}/lab/p176/observer"

ALLOWED_ZONE="asia-northeast3-a"
TARGET_INSTANCE="p176-live-target"
OBSERVER_INSTANCE="p176-live-observer"
TARGET_PRIVATE_IP="10.176.0.10"
OBSERVER_PRIVATE_IP="10.176.0.20"
TARGET_LOOPBACK_PORT="8020"
OBSERVER_LOOPBACK_PORT="8030"

forbidden_projects=()
if [[ -n "${P176_FORBIDDEN_PROJECT_IDS:-}" ]]; then
  IFS=', ' read -r -a forbidden_projects <<<"${P176_FORBIDDEN_PROJECT_IDS}"
fi

usage() {
  cat <<'USAGE'
Usage:
  runtime-iap.sh plan
  runtime-iap.sh run

Required environment:
  EXPECTED_PROJECT_ID              Dedicated opscat-p176-live-* project ID.

Plan environment:
  REVIEWED_APPLY_PLAN_ARTIFACT
  REVIEWED_TEARDOWN_PLAN_ARTIFACT
  REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT
  REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT
  P176_RUNTIME_PLAN_DIR            Optional /tmp/opscat-p176-runtime-* output dir.

Run environment:
  P176_RUNTIME_PLAN_FILE           Plan file created by "plan".
  EXPECTED_P176_RUNTIME_PLAN_SHA256
  P176_RUNTIME_RUN_DIR             Optional local run artifact dir.

This script uses gcloud compute ssh/scp with --tunnel-through-iap only. It does
not run Terraform, apply, destroy, or mutate Terraform state. The reviewed
runtime source bundle is deployed to the two disposable P176 VMs before the
IAP-only bridge is opened.
USAGE
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

project_id() {
  : "${EXPECTED_PROJECT_ID:?set EXPECTED_PROJECT_ID to the frozen P176 live project ID}"
  if [[ ! "${EXPECTED_PROJECT_ID}" =~ ^opscat-p176-live-[a-z0-9-]{6,20}$ ]]; then
    die "EXPECTED_PROJECT_ID must be a dedicated opscat-p176-live-* project"
  fi
  for forbidden in "${forbidden_projects[@]:-}"; do
    [[ -n "${forbidden}" ]] || continue
    if [[ "${EXPECTED_PROJECT_ID}" == "${forbidden}" ]]; then
      die "forbidden project is not a P176 live project"
    fi
  done
  printf '%s\n' "${EXPECTED_PROJECT_ID}"
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

timestamp() {
  date -u +"%Y%m%dT%H%M%SZ"
}

write_plan_sha() {
  local plan_file="$1"
  local digest
  digest="$(sha256_file "${plan_file}")"
  printf '%s  %s\n' "${digest}" "${plan_file}" >"${plan_file}.sha256"
  echo "${digest}"
}

validate_plan_digest() {
  local plan_file="$1"
  local expected="$2"
  [[ -f "${plan_file}" ]] || die "missing plan file: ${plan_file}"
  [[ -n "${expected}" ]] || die "EXPECTED_P176_RUNTIME_PLAN_SHA256 is required"
  local actual
  actual="$(sha256_file "${plan_file}")"
  [[ "${actual}" == "${expected}" ]] || die "plan digest mismatch: expected ${expected}, got ${actual}"
}

new_work_dir() {
  local requested="${P176_RUNTIME_PLAN_DIR:-}"
  if [[ -n "${requested}" ]]; then
    [[ "${requested}" == /tmp/opscat-p176-runtime-* ]] || die "P176_RUNTIME_PLAN_DIR must be under /tmp/opscat-p176-runtime-*"
    [[ ! -e "${requested}" ]] || die "P176_RUNTIME_PLAN_DIR must not already exist"
    mkdir -m 0700 "${requested}"
    printf '%s\n' "${requested}"
    return
  fi
  mktemp -d /tmp/opscat-p176-runtime-XXXXXXXX
}

require_reviewed_artifact() {
  local path="$1"
  local label="$2"
  [[ -f "${path}" && ! -L "${path}" ]] || die "missing or unsafe reviewed artifact: ${label}"
}

make_runtime_plan() {
  require_command shasum
  local project created work_dir plan_file plan_sha
  project="$(project_id)"
  created="$(timestamp)"
  work_dir="$(new_work_dir)"
  plan_file="${work_dir}/p176-runtime-plan.env"

  require_reviewed_artifact "${REVIEWED_APPLY_PLAN_ARTIFACT:?set REVIEWED_APPLY_PLAN_ARTIFACT}" "apply"
  require_reviewed_artifact "${REVIEWED_TEARDOWN_PLAN_ARTIFACT:?set REVIEWED_TEARDOWN_PLAN_ARTIFACT}" "teardown"
  require_reviewed_artifact "${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT:?set REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}" "cost-cutoff-apply"
  require_reviewed_artifact "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT:?set REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}" "cost-cutoff-destroy"
  validate_runtime_sources

  cat >"${plan_file}" <<EOF
PLAN_KIND=p176-runtime-entry
CREATED_AT=${created}
PROJECT_ID=${project}
ZONE=${ALLOWED_ZONE}
TARGET_VM=${TARGET_INSTANCE}
OBSERVER_VM=${OBSERVER_INSTANCE}
TARGET_BIND_IP=${TARGET_PRIVATE_IP}
OBSERVER_BIND_IP=${OBSERVER_PRIVATE_IP}
TARGET_LOOPBACK_PORT=${TARGET_LOOPBACK_PORT}
OBSERVER_LOOPBACK_PORT=${OBSERVER_LOOPBACK_PORT}
REVIEWED_APPLY_PLAN_ARTIFACT=${REVIEWED_APPLY_PLAN_ARTIFACT}
REVIEWED_APPLY_PLAN_SHA256=$(sha256_file "${REVIEWED_APPLY_PLAN_ARTIFACT}")
REVIEWED_TEARDOWN_PLAN_ARTIFACT=${REVIEWED_TEARDOWN_PLAN_ARTIFACT}
REVIEWED_TEARDOWN_PLAN_SHA256=$(sha256_file "${REVIEWED_TEARDOWN_PLAN_ARTIFACT}")
REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT=${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}
REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256=$(sha256_file "${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}")
REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT=${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}
REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256=$(sha256_file "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}")
RUNTIME_SOURCE_MANIFEST_SHA256=$(runtime_source_manifest_sha256)
ORCHESTRATOR_SHA256=$(sha256_file "${BASH_SOURCE[0]}")
EOF
  plan_sha="$(write_plan_sha "${plan_file}")"
  echo "P176 runtime plan-only complete."
  echo "P176 runtime plan file: ${plan_file}"
  echo "P176 runtime plan sha256: ${plan_sha}"
  echo "Review the plan, then run with P176_RUNTIME_PLAN_FILE and EXPECTED_P176_RUNTIME_PLAN_SHA256."
}

load_runtime_plan() {
  local plan_file="$1"
  local line key value seen_keys="|"
  unset PLAN_KIND CREATED_AT PROJECT_ID ZONE TARGET_VM OBSERVER_VM
  unset TARGET_BIND_IP OBSERVER_BIND_IP TARGET_LOOPBACK_PORT OBSERVER_LOOPBACK_PORT
  unset REVIEWED_APPLY_PLAN_ARTIFACT REVIEWED_APPLY_PLAN_SHA256
  unset REVIEWED_TEARDOWN_PLAN_ARTIFACT REVIEWED_TEARDOWN_PLAN_SHA256
  unset REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256
  unset REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256
  unset RUNTIME_SOURCE_MANIFEST_SHA256 ORCHESTRATOR_SHA256
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^([A-Z0-9_]+)=([^[:space:]]+)$ ]] || die "invalid P176 runtime plan line"
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    case "${key}" in
      PLAN_KIND|CREATED_AT|PROJECT_ID|ZONE|TARGET_VM|OBSERVER_VM|TARGET_BIND_IP|OBSERVER_BIND_IP|TARGET_LOOPBACK_PORT|OBSERVER_LOOPBACK_PORT|REVIEWED_APPLY_PLAN_ARTIFACT|REVIEWED_APPLY_PLAN_SHA256|REVIEWED_TEARDOWN_PLAN_ARTIFACT|REVIEWED_TEARDOWN_PLAN_SHA256|REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT|REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256|REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT|REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256|RUNTIME_SOURCE_MANIFEST_SHA256|ORCHESTRATOR_SHA256) ;;
      *) die "unexpected P176 runtime plan key: ${key}" ;;
    esac
    [[ "${seen_keys}" != *"|${key}|"* ]] || die "duplicate P176 runtime plan key: ${key}"
    seen_keys="${seen_keys}${key}|"
    printf -v "${key}" '%s' "${value}"
  done <"${plan_file}"
  : "${PLAN_KIND:?missing PLAN_KIND in P176 runtime plan}"
  : "${PROJECT_ID:?missing PROJECT_ID in P176 runtime plan}"
  : "${ZONE:?missing ZONE in P176 runtime plan}"
  : "${TARGET_VM:?missing TARGET_VM in P176 runtime plan}"
  : "${OBSERVER_VM:?missing OBSERVER_VM in P176 runtime plan}"
  : "${TARGET_BIND_IP:?missing TARGET_BIND_IP in P176 runtime plan}"
  : "${OBSERVER_BIND_IP:?missing OBSERVER_BIND_IP in P176 runtime plan}"
  : "${TARGET_LOOPBACK_PORT:?missing TARGET_LOOPBACK_PORT in P176 runtime plan}"
  : "${OBSERVER_LOOPBACK_PORT:?missing OBSERVER_LOOPBACK_PORT in P176 runtime plan}"
  : "${REVIEWED_APPLY_PLAN_ARTIFACT:?missing REVIEWED_APPLY_PLAN_ARTIFACT in P176 runtime plan}"
  : "${REVIEWED_APPLY_PLAN_SHA256:?missing REVIEWED_APPLY_PLAN_SHA256 in P176 runtime plan}"
  : "${REVIEWED_TEARDOWN_PLAN_ARTIFACT:?missing REVIEWED_TEARDOWN_PLAN_ARTIFACT in P176 runtime plan}"
  : "${REVIEWED_TEARDOWN_PLAN_SHA256:?missing REVIEWED_TEARDOWN_PLAN_SHA256 in P176 runtime plan}"
  : "${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT:?missing REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT in P176 runtime plan}"
  : "${REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256:?missing REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256 in P176 runtime plan}"
  : "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT:?missing REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT in P176 runtime plan}"
  : "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256:?missing REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256 in P176 runtime plan}"
  : "${RUNTIME_SOURCE_MANIFEST_SHA256:?missing RUNTIME_SOURCE_MANIFEST_SHA256 in P176 runtime plan}"
  : "${ORCHESTRATOR_SHA256:?missing ORCHESTRATOR_SHA256 in P176 runtime plan}"
  [[ "${PLAN_KIND}" == "p176-runtime-entry" ]] || die "P176_RUNTIME_PLAN_FILE is not a runtime entry plan"
  [[ "${PROJECT_ID}" == "$(project_id)" ]] || die "P176 runtime plan project does not match EXPECTED_PROJECT_ID"
  [[ "${ZONE}" == "${ALLOWED_ZONE}" ]] || die "P176 runtime plan zone is not allowed"
  [[ "${TARGET_VM}" == "${TARGET_INSTANCE}" ]] || die "P176 runtime plan target instance is not allowed"
  [[ "${OBSERVER_VM}" == "${OBSERVER_INSTANCE}" ]] || die "P176 runtime plan observer instance is not allowed"
  [[ "${TARGET_BIND_IP}" == "${TARGET_PRIVATE_IP}" ]] || die "P176 runtime target private IP is not allowed"
  [[ "${OBSERVER_BIND_IP}" == "${OBSERVER_PRIVATE_IP}" ]] || die "P176 runtime observer private IP is not allowed"
  [[ "${TARGET_LOOPBACK_PORT}" == "8020" ]] || die "P176 target loopback port is not allowed"
  [[ "${OBSERVER_LOOPBACK_PORT}" == "8030" ]] || die "P176 observer loopback port is not allowed"
}

validate_reviewed_artifacts() {
  require_reviewed_artifact "${REVIEWED_APPLY_PLAN_ARTIFACT}" "apply"
  require_reviewed_artifact "${REVIEWED_TEARDOWN_PLAN_ARTIFACT}" "teardown"
  require_reviewed_artifact "${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}" "cost-cutoff-apply"
  require_reviewed_artifact "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}" "cost-cutoff-destroy"
  [[ "$(sha256_file "${REVIEWED_APPLY_PLAN_ARTIFACT}")" == "${REVIEWED_APPLY_PLAN_SHA256}" ]] || die "reviewed apply plan digest mismatch"
  [[ "$(sha256_file "${REVIEWED_TEARDOWN_PLAN_ARTIFACT}")" == "${REVIEWED_TEARDOWN_PLAN_SHA256}" ]] || die "reviewed teardown plan digest mismatch"
  [[ "$(sha256_file "${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}")" == "${REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256}" ]] || die "reviewed cost-cutoff apply plan digest mismatch"
  [[ "$(sha256_file "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}")" == "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256}" ]] || die "reviewed cost-cutoff destroy plan digest mismatch"
  [[ "$(sha256_file "${BASH_SOURCE[0]}")" == "${ORCHESTRATOR_SHA256}" ]] || die "P176 runtime orchestrator digest mismatch"
}

require_runtime_source() {
  local path="$1"
  [[ -f "${path}" && ! -L "${path}" ]] || die "missing or unsafe P176 runtime source: ${path}"
}

validate_runtime_sources() {
  require_runtime_source "${REPO_ROOT}/app/services/p176_live_runtime.py"
  require_runtime_source "${REPO_ROOT}/app/services/p176_runtime_bridge.py"
  require_runtime_source "${REPO_ROOT}/scripts/run_p176_live_runtime_bridge.py"
  require_runtime_source "${LIVE_LAB_DIR}/docker-compose.yml"
  require_runtime_source "${LIVE_LAB_DIR}/docker-compose.runtime.yml"
  require_runtime_source "${LIVE_LAB_DIR}/fault_controller.py"
  require_runtime_source "${LIVE_LAB_DIR}/service_stub.py"
  require_runtime_source "${LIVE_LAB_DIR}/telemetry_collector.py"
  require_runtime_source "${LIVE_LAB_DIR}/topology.json"
  require_runtime_source "${OBSERVER_LAB_DIR}/docker-compose.yml"
}

runtime_source_manifest() {
  local relative
  for relative in \
    app/services/p176_live_runtime.py \
    app/services/p176_runtime_bridge.py \
    scripts/run_p176_live_runtime_bridge.py \
    lab/p176/live/docker-compose.yml \
    lab/p176/live/docker-compose.runtime.yml \
    lab/p176/live/fault_controller.py \
    lab/p176/live/service_stub.py \
    lab/p176/live/telemetry_collector.py \
    lab/p176/live/topology.json \
    lab/p176/observer/docker-compose.yml; do
    printf '%s\t%s\n' "${relative}" "$(sha256_file "${REPO_ROOT}/${relative}")"
  done
}

runtime_source_manifest_sha256() {
  runtime_source_manifest | shasum -a 256 | awk '{print $1}'
}

validate_runtime_source_digest() {
  [[ "$(runtime_source_manifest_sha256)" == "${RUNTIME_SOURCE_MANIFEST_SHA256}" ]] \
    || die "runtime source manifest digest mismatch"
}

copy_reviewed_artifact() {
  local source="$1"
  local expected_digest="$2"
  local destination="$3"
  local label="$4"
  if [[ -e "${destination}" || -L "${destination}" ]]; then
    [[ -f "${destination}" && ! -L "${destination}" ]] || die "unsafe existing run artifact: ${label}"
    [[ "$(sha256_file "${destination}")" == "${expected_digest}" ]] || die "existing run artifact digest mismatch: ${label}"
    return
  fi
  cp "${source}" "${destination}"
  chmod 0400 "${destination}"
  [[ -f "${destination}" && ! -L "${destination}" ]] || die "unsafe copied run artifact: ${label}"
  [[ "$(sha256_file "${destination}")" == "${expected_digest}" ]] || die "copied run artifact digest mismatch: ${label}"
}

materialize_reviewed_artifacts() {
  local run_dir="$1"
  [[ ! -L "${run_dir}" ]] || die "P176_RUNTIME_RUN_DIR must not be a symlink"
  mkdir -p "${run_dir}"
  [[ -d "${run_dir}" && ! -L "${run_dir}" ]] || die "P176_RUNTIME_RUN_DIR is unsafe"

  RUN_REVIEWED_APPLY_PLAN_ARTIFACT="${run_dir}/reviewed-p176-live-apply.plan"
  RUN_REVIEWED_TEARDOWN_PLAN_ARTIFACT="${run_dir}/reviewed-p176-live-destroy.plan"
  RUN_REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT="${run_dir}/reviewed-p176-cost-cutoff-apply.plan"
  RUN_REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT="${run_dir}/reviewed-p176-cost-cutoff-destroy.plan"

  copy_reviewed_artifact "${REVIEWED_APPLY_PLAN_ARTIFACT}" "${REVIEWED_APPLY_PLAN_SHA256}" "${RUN_REVIEWED_APPLY_PLAN_ARTIFACT}" "apply"
  copy_reviewed_artifact "${REVIEWED_TEARDOWN_PLAN_ARTIFACT}" "${REVIEWED_TEARDOWN_PLAN_SHA256}" "${RUN_REVIEWED_TEARDOWN_PLAN_ARTIFACT}" "teardown"
  copy_reviewed_artifact "${REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}" "${REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256}" "${RUN_REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}" "cost-cutoff-apply"
  copy_reviewed_artifact "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}" "${REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256}" "${RUN_REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}" "cost-cutoff-destroy"
}

deploy_runtime_services() {
  local run_dir="$1"
  local capability_file="$2"
  local bundle_dir="${run_dir}/runtime-deploy-bundles"
  local observer_staging="${bundle_dir}/observer"
  local target_bundle="${bundle_dir}/target-runtime.tgz"
  local observer_bundle="${bundle_dir}/observer-runtime.tgz"
  mkdir -m 0700 "${bundle_dir}"
  mkdir -m 0700 "${observer_staging}"

  tar -C "${LIVE_LAB_DIR}" -czf "${target_bundle}" .
  cp "${LIVE_LAB_DIR}/telemetry_collector.py" "${observer_staging}/telemetry_collector.py"
  cp "${OBSERVER_LAB_DIR}/docker-compose.yml" "${observer_staging}/docker-compose.yml"
  chmod 0444 "${observer_staging}/telemetry_collector.py"
  chmod 0400 "${observer_staging}/docker-compose.yml"
  tar -C "${observer_staging}" -czf "${observer_bundle}" .
  chmod 0400 "${target_bundle}" "${observer_bundle}"

  gcloud compute scp "${target_bundle}" "${TARGET_VM}:/tmp/p176-target-runtime.tgz" \
    --project "${PROJECT_ID}" --zone "${ZONE}" --tunnel-through-iap --quiet
  gcloud compute scp "${capability_file}" "${TARGET_VM}:/tmp/p176-runtime-capability.env" \
    --project "${PROJECT_ID}" --zone "${ZONE}" --tunnel-through-iap --quiet
  gcloud compute ssh "${TARGET_VM}" \
    --project "${PROJECT_ID}" --zone "${ZONE}" --tunnel-through-iap --quiet \
    --command "sudo install -d -m 0755 /opt/opscat/p176-live/workload && sudo tar -xzf /tmp/p176-target-runtime.tgz -C /opt/opscat/p176-live/workload && sudo install -m 0400 /tmp/p176-runtime-capability.env /opt/opscat/p176-live/runtime-capability.env && sudo rm -f /tmp/p176-target-runtime.tgz /tmp/p176-runtime-capability.env && sudo docker compose --env-file /opt/opscat/p176-live/runtime-capability.env --project-directory /opt/opscat/p176-live/workload -f /opt/opscat/p176-live/workload/docker-compose.yml -f /opt/opscat/p176-live/workload/docker-compose.runtime.yml up -d --remove-orphans"

  gcloud compute scp "${observer_bundle}" "${OBSERVER_VM}:/tmp/p176-observer-runtime.tgz" \
    --project "${PROJECT_ID}" --zone "${ZONE}" --tunnel-through-iap --quiet
  gcloud compute ssh "${OBSERVER_VM}" \
    --project "${PROJECT_ID}" --zone "${ZONE}" --tunnel-through-iap --quiet \
    --command "sudo install -d -m 0755 /opt/opscat/p176-live/observer && sudo tar -xzf /tmp/p176-observer-runtime.tgz -C /opt/opscat/p176-live/observer && sudo chmod 0755 /opt/opscat/p176-live/observer && sudo chmod 0444 /opt/opscat/p176-live/observer/telemetry_collector.py && sudo chmod 0400 /opt/opscat/p176-live/observer/docker-compose.yml && sudo rm -f /tmp/p176-observer-runtime.tgz && sudo docker compose --project-directory /opt/opscat/p176-live/observer -f /opt/opscat/p176-live/observer/docker-compose.yml up -d --remove-orphans"
}

new_capability_file() {
  local path
  path="$(mktemp "${TMPDIR:-/tmp}/p176-runtime-capability.XXXXXX")"
  chmod 0600 "${path}"
  printf 'P176_FAULT_CAPABILITY_TOKEN=%s\n' "$(openssl rand -hex 32)" >"${path}"
  printf '%s\n' "${path}"
}

cleanup_remote_capability() {
  gcloud compute ssh "${TARGET_VM}" \
    --project "${PROJECT_ID}" --zone "${ZONE}" --tunnel-through-iap --quiet \
    --command "sudo docker compose --env-file /opt/opscat/p176-live/runtime-capability.env --project-directory /opt/opscat/p176-live/workload -f /opt/opscat/p176-live/workload/docker-compose.yml -f /opt/opscat/p176-live/workload/docker-compose.runtime.yml stop fault-controller >/dev/null 2>&1 || true; sudo rm -f /opt/opscat/p176-live/runtime-capability.env" \
    >/dev/null 2>&1 || true
}

allocate_loopback_port() {
  "${PYTHON_BIN:-python3}" -c 'import socket; sock=socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()'
}

start_iap_loopback_tunnel() {
  local instance="$1"
  local local_port="$2"
  local remote_host="$3"
  local remote_port="$4"
  local log_file="$5"
  local pid_var="$6"
  case "${remote_host}" in
    127.0.0.1|10.176.0.10) ;;
    *) die "P176 tunnel remote host is not allowed: ${remote_host}" ;;
  esac
  gcloud compute ssh "${instance}" \
    --project "${PROJECT_ID}" \
    --zone "${ZONE}" \
    --tunnel-through-iap \
    -- -N -o ExitOnForwardFailure=yes \
    -L "127.0.0.1:${local_port}:${remote_host}:${remote_port}" >"${log_file}" 2>&1 &
  printf -v "${pid_var}" '%s' "$!"
}

wait_loopback_ready() {
  local pid="$1"
  local log_file="$2"
  local url="$3"
  local label="$4"
  for _attempt in $(seq 1 30); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      cat "${log_file}" >&2
      die "IAP SSH ${label} tunnel exited before readiness"
    fi
    if curl -fsS --max-time 2 "${url}" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  die "IAP SSH ${label} tunnel did not become ready"
}

run_runtime_entry() {
  require_command curl
  require_command gcloud
  require_command openssl
  require_command shasum
  require_command tar
  local plan_file expected target_local_port observer_local_port target_log observer_log target_pid="" observer_pid="" cleanup_cmd run_dir capability_file capability_token
  plan_file="${P176_RUNTIME_PLAN_FILE:?set P176_RUNTIME_PLAN_FILE to the reviewed P176 runtime plan}"
  expected="${EXPECTED_P176_RUNTIME_PLAN_SHA256:?set EXPECTED_P176_RUNTIME_PLAN_SHA256 to the reviewed P176 runtime plan sha256}"
  validate_plan_digest "${plan_file}" "${expected}"
  load_runtime_plan "${plan_file}"
  validate_reviewed_artifacts
  validate_runtime_sources
  validate_runtime_source_digest

  run_dir="${P176_RUNTIME_RUN_DIR:-${REPO_ROOT}/evals/p176/live-runtime/$(timestamp)}"
  materialize_reviewed_artifacts "${run_dir}"
  if [[ "${P176_RUNTIME_PHASE:-collect}" == "finalize" ]]; then
    (
      cd "${REPO_ROOT}"
      "${PYTHON_BIN:-python3}" scripts/run_p176_live_runtime_bridge.py \
        --run-dir "${run_dir}" \
        --target-endpoint "http://127.0.0.1:1" \
        --observer-endpoint "http://127.0.0.1:1" \
        --reviewed-apply-plan-artifact "${RUN_REVIEWED_APPLY_PLAN_ARTIFACT}" \
        --reviewed-teardown-plan-artifact "${RUN_REVIEWED_TEARDOWN_PLAN_ARTIFACT}" \
        --reviewed-cost-cutoff-apply-plan-artifact "${RUN_REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}" \
        --reviewed-cost-cutoff-destroy-plan-artifact "${RUN_REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}"
    )
    return
  fi
  [[ "${P176_RUNTIME_PHASE:-collect}" == "collect" ]] || die "P176_RUNTIME_PHASE must be collect or finalize"
  capability_file="$(new_capability_file)"
  capability_token="$(cut -d= -f2 "${capability_file}")"
  [[ "${capability_token}" =~ ^[0-9a-f]{64}$ ]] || die "failed to create runtime capability"
  printf -v cleanup_cmd 'rm -f -- %q' "${capability_file}"
  trap "${cleanup_cmd}" EXIT
  deploy_runtime_services "${run_dir}" "${capability_file}"

  target_local_port="$(allocate_loopback_port)"
  observer_local_port="$(allocate_loopback_port)"
  [[ "${target_local_port}" =~ ^[0-9]+$ && "${observer_local_port}" =~ ^[0-9]+$ && "${target_local_port}" != "${observer_local_port}" ]] \
    || die "failed to allocate distinct local tunnel ports"
  target_log="$(mktemp "${TMPDIR:-/tmp}/p176-target-iap-tunnel.XXXXXX")"
  observer_log="$(mktemp "${TMPDIR:-/tmp}/p176-observer-iap-tunnel.XXXXXX")"
  start_iap_loopback_tunnel "${TARGET_VM}" "${target_local_port}" "${TARGET_BIND_IP}" "${TARGET_LOOPBACK_PORT}" "${target_log}" target_pid
  printf -v cleanup_cmd 'cleanup_remote_capability; kill %q 2>/dev/null || true; wait %q 2>/dev/null || true; rm -f -- %q %q %q' "${target_pid}" "${target_pid}" "${target_log}" "${observer_log}" "${capability_file}"
  trap "${cleanup_cmd}" EXIT
  start_iap_loopback_tunnel "${OBSERVER_VM}" "${observer_local_port}" "127.0.0.1" "${OBSERVER_LOOPBACK_PORT}" "${observer_log}" observer_pid
  printf -v cleanup_cmd 'cleanup_remote_capability; kill %q %q 2>/dev/null || true; wait %q %q 2>/dev/null || true; rm -f -- %q %q %q' "${target_pid}" "${observer_pid}" "${target_pid}" "${observer_pid}" "${target_log}" "${observer_log}" "${capability_file}"
  trap "${cleanup_cmd}" EXIT
  wait_loopback_ready "${target_pid}" "${target_log}" "http://127.0.0.1:${target_local_port}/health" "target"
  wait_loopback_ready "${observer_pid}" "${observer_log}" "http://127.0.0.1:${observer_local_port}/health" "observer"

  (
    cd "${REPO_ROOT}"
    P176_FAULT_CAPABILITY_TOKEN="${capability_token}" "${PYTHON_BIN:-python3}" scripts/run_p176_live_runtime_bridge.py \
      --run-dir "${run_dir}" \
      --target-endpoint "http://127.0.0.1:${target_local_port}" \
      --observer-endpoint "http://127.0.0.1:${observer_local_port}" \
      --reviewed-apply-plan-artifact "${RUN_REVIEWED_APPLY_PLAN_ARTIFACT}" \
      --reviewed-teardown-plan-artifact "${RUN_REVIEWED_TEARDOWN_PLAN_ARTIFACT}" \
      --reviewed-cost-cutoff-apply-plan-artifact "${RUN_REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT}" \
      --reviewed-cost-cutoff-destroy-plan-artifact "${RUN_REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT}"
  )
  kill "${target_pid}" "${observer_pid}" 2>/dev/null || true
  wait "${target_pid}" "${observer_pid}" 2>/dev/null || true
  cleanup_remote_capability
  rm -f -- "${target_log}" "${observer_log}" "${capability_file}"
  trap - EXIT
}

main() {
  local command_name="${1:-}"
  case "${command_name}" in
    plan) make_runtime_plan ;;
    run) run_runtime_entry ;;
    -h|--help|help) usage ;;
    *) usage >&2; exit 2 ;;
  esac
}

main "$@"
