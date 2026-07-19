#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LAB_DIR="${REPO_ROOT}/lab/p174"
HOST_COLLECTOR="${SCRIPT_DIR}/observer-host-evidence-collector.sh"

ALLOWED_ZONE="asia-northeast3-a"
TARGET_INSTANCE="p174-target"
OBSERVER_INSTANCE="p174-observer"
TARGET_PRIVATE_IP="10.174.0.10"
OBSERVER_PRIVATE_IP="10.174.0.20"
REMOTE_BASE="/opt/opscat/p174"
REMOTE_ARCHIVE="/tmp/opscat-p174-lab-bundle.tgz"

forbidden_projects=()
if [[ -n "${P174_FORBIDDEN_PROJECT_IDS:-}" ]]; then
  IFS=', ' read -r -a forbidden_projects <<<"${P174_FORBIDDEN_PROJECT_IDS}"
fi

usage() {
  cat <<'USAGE'
Usage:
  workload-iap.sh plan
  workload-iap.sh apply
  workload-iap.sh evidence
  workload-iap.sh action-dry-run
  workload-iap.sh action
  workload-iap.sh p175-plan
  workload-iap.sh p175-live
  workload-iap.sh teardown-plan
  workload-iap.sh teardown-apply

Required environment:
  EXPECTED_PROJECT_ID              Dedicated opscat-p174-* project ID.

Apply environment:
  PLAN_FILE                        Plan file created by "plan".
  EXPECTED_PLAN_SHA256             SHA-256 from PLAN_FILE.sha256.
  APPLY_REVIEWED_WORKLOAD=1        Required before copying or running on VMs.

Evidence environment:
  PLAN_FILE                        Plan file created by "plan".
  EXPECTED_PLAN_SHA256             SHA-256 from PLAN_FILE.sha256.
  EVIDENCE_DIR                     Optional local evidence directory.

Action environment:
  PLAN_FILE                        Reviewed workload deployment plan.
  EXPECTED_PLAN_SHA256             SHA-256 from PLAN_FILE.sha256.
  P174_ACTION                      tune_pool, restart_worker, or rollback_canary.
  P174_REQUEST_ID                  Unique request ID.
  P174_POOL_SIZE                   tune_pool target, 1..64 (default 16).
  APPLY_REVIEWED_ACTION=1          Required for non-dry-run action.

P175 plan environment:
  PLAN_FILE                        Reviewed workload deployment plan.
  EXPECTED_PLAN_SHA256             SHA-256 from PLAN_FILE.sha256.
  P175_REVIEWED_HARNESS=1          Required to freeze reviewed harness manifest.
  P175_REVIEWER_ID                 Reviewer ID for the harness manifest.
  P175_SEED                        Optional deterministic campaign seed.

P175 live environment:
  P175_PLAN_FILE                   Plan file created by "p175-plan".
  EXPECTED_P175_PLAN_SHA256        SHA-256 from P175_PLAN_FILE.sha256.
  EXPECTED_HARNESS_MANIFEST_SHA256 Reviewed harness manifest SHA-256.
  P175_MAX_SCENARIOS               Optional diagnostic-only harness limit.

Teardown apply environment:
  PLAN_FILE                        Plan file created by "teardown-plan".
  EXPECTED_PLAN_SHA256             SHA-256 from PLAN_FILE.sha256.
  APPLY_REVIEWED_WORKLOAD_TEARDOWN=1

This script uses gcloud compute ssh/scp with --tunnel-through-iap only. It does
not create, modify, or destroy Terraform resources.
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
  : "${EXPECTED_PROJECT_ID:?set EXPECTED_PROJECT_ID to the frozen P174 project ID}"
  if [[ ! "${EXPECTED_PROJECT_ID}" =~ ^opscat-p174-[a-z0-9-]{6,20}$ ]]; then
    die "EXPECTED_PROJECT_ID must be a dedicated opscat-p174-* project"
  fi
  for forbidden in "${forbidden_projects[@]:-}"; do
    [[ -n "${forbidden}" ]] || continue
    if [[ "${EXPECTED_PROJECT_ID}" == "${forbidden}" ]]; then
      die "forbidden project is not a P174 lab project"
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
  [[ -n "${expected}" ]] || die "EXPECTED_PLAN_SHA256 is required"
  local actual
  actual="$(sha256_file "${plan_file}")"
  [[ "${actual}" == "${expected}" ]] || die "plan digest mismatch: expected ${expected}, got ${actual}"
}

load_plan() {
  local plan_file="$1"
  local line key value seen_keys="|"
  unset PLAN_KIND CREATED_AT PROJECT_ID ZONE TARGET_VM OBSERVER_VM
  unset TARGET_BIND_IP OBSERVER_BIND_IP BUNDLE_PATH BUNDLE_SHA256
  unset BUNDLE_MANIFEST_SHA256 HOST_COLLECTOR_SHA256 REMOTE_BASE
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^([A-Z0-9_]+)=([A-Za-z0-9._/:=-]+)$ ]] || die "invalid plan line"
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    case "${key}" in
      PLAN_KIND|CREATED_AT|PROJECT_ID|ZONE|TARGET_VM|OBSERVER_VM|TARGET_BIND_IP|OBSERVER_BIND_IP|BUNDLE_PATH|BUNDLE_SHA256|BUNDLE_MANIFEST_SHA256|HOST_COLLECTOR_SHA256|REMOTE_BASE) ;;
      *) die "unexpected plan key: ${key}" ;;
    esac
    [[ "${seen_keys}" != *"|${key}|"* ]] || die "duplicate plan key: ${key}"
    seen_keys="${seen_keys}${key}|"
    printf -v "${key}" '%s' "${value}"
  done <"${plan_file}"
  : "${PLAN_KIND:?missing PLAN_KIND in plan}"
  : "${CREATED_AT:?missing CREATED_AT in plan}"
  : "${PROJECT_ID:?missing PROJECT_ID in plan}"
  : "${ZONE:?missing ZONE in plan}"
  : "${TARGET_VM:?missing TARGET_VM in plan}"
  : "${OBSERVER_VM:?missing OBSERVER_VM in plan}"
  : "${TARGET_BIND_IP:?missing TARGET_BIND_IP in plan}"
  : "${OBSERVER_BIND_IP:?missing OBSERVER_BIND_IP in plan}"
  : "${REMOTE_BASE:?missing REMOTE_BASE in plan}"
  case "${PLAN_KIND}" in
    workload-deploy)
      : "${BUNDLE_PATH:?missing BUNDLE_PATH in workload deployment plan}"
      : "${BUNDLE_SHA256:?missing BUNDLE_SHA256 in workload deployment plan}"
      : "${BUNDLE_MANIFEST_SHA256:?missing BUNDLE_MANIFEST_SHA256 in workload deployment plan}"
      : "${HOST_COLLECTOR_SHA256:?missing HOST_COLLECTOR_SHA256 in workload deployment plan}"
      ;;
    workload-teardown) ;;
    *) die "unsupported PLAN_KIND: ${PLAN_KIND}" ;;
  esac
  [[ "${PROJECT_ID}" == "$(project_id)" ]] || die "plan project ${PROJECT_ID} does not match EXPECTED_PROJECT_ID"
  [[ "${ZONE}" == "${ALLOWED_ZONE}" ]] || die "plan zone ${ZONE} is not allowed"
  [[ "${TARGET_VM}" == "${TARGET_INSTANCE}" ]] || die "plan target instance ${TARGET_VM} is not allowed"
  [[ "${OBSERVER_VM}" == "${OBSERVER_INSTANCE}" ]] || die "plan observer instance ${OBSERVER_VM} is not allowed"
  [[ "${TARGET_BIND_IP}" == "${TARGET_PRIVATE_IP}" ]] || die "plan target private bind IP ${TARGET_BIND_IP} is not allowed"
  [[ "${OBSERVER_BIND_IP}" == "${OBSERVER_PRIVATE_IP}" ]] || die "plan observer private IP ${OBSERVER_BIND_IP} is not allowed"
}

new_work_dir() {
  local requested="${WORKLOAD_PLAN_DIR:-}"
  if [[ -n "${requested}" ]]; then
    [[ "${requested}" == /tmp/opscat-p174-workload-* ]] || die "WORKLOAD_PLAN_DIR must be under /tmp/opscat-p174-workload-*"
    [[ ! -e "${requested}" ]] || die "WORKLOAD_PLAN_DIR must not already exist"
    mkdir -m 0700 "${requested}"
    printf '%s\n' "${requested}"
    return
  fi
  mktemp -d /tmp/opscat-p174-workload-XXXXXXXX
}

gcloud_ssh() {
  local instance="$1"
  local command_text="$2"
  gcloud compute ssh "${instance}" \
    --project "${PROJECT_ID}" \
    --zone "${ZONE}" \
    --tunnel-through-iap \
    --command "${command_text}"
}

gcloud_scp_to() {
  local source="$1"
  local instance="$2"
  local dest="$3"
  gcloud compute scp "${source}" "${instance}:${dest}" \
    --project "${PROJECT_ID}" \
    --zone "${ZONE}" \
    --tunnel-through-iap
}

gcloud_scp_from() {
  local instance="$1"
  local source="$2"
  local dest="$3"
  gcloud compute scp "${instance}:${source}" "${dest}" \
    --project "${PROJECT_ID}" \
    --zone "${ZONE}" \
    --tunnel-through-iap
}

make_bundle_plan() {
  local project
  project="$(project_id)"
  require_command find
  require_command shasum
  require_command tar

  [[ -f "${LAB_DIR}/docker-compose.target.yml" ]] || die "missing lab bundle at ${LAB_DIR}"
  [[ -f "${HOST_COLLECTOR}" ]] || die "missing observer host collector at ${HOST_COLLECTOR}"

  local created work_dir stage bundle manifest bundle_sha manifest_sha plan_file plan_sha
  created="$(timestamp)"
  work_dir="$(new_work_dir)"
  stage="${work_dir}/bundle"
  bundle="${work_dir}/opscat-p174-lab-bundle.tgz"
  manifest="${work_dir}/bundle-files.sha256"
  plan_file="${work_dir}/workload-plan.env"

  mkdir -p "${stage}"
  tar -C "${LAB_DIR}" \
    --exclude='./runtime' \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.DS_Store' \
    -cf - . | tar -C "${stage}" -xf -

  (
    cd "${stage}"
    find . -type f | LC_ALL=C sort | while IFS= read -r file; do
      shasum -a 256 "${file#./}"
    done
  ) >"${manifest}"
  cp "${manifest}" "${stage}/bundle-files.sha256"
  tar -C "${stage}" -czf "${bundle}" .

  bundle_sha="$(sha256_file "${bundle}")"
  manifest_sha="$(sha256_file "${manifest}")"
  cat >"${plan_file}" <<EOF
PLAN_KIND=workload-deploy
CREATED_AT=${created}
PROJECT_ID=${project}
ZONE=${ALLOWED_ZONE}
TARGET_VM=${TARGET_INSTANCE}
OBSERVER_VM=${OBSERVER_INSTANCE}
TARGET_BIND_IP=${TARGET_PRIVATE_IP}
OBSERVER_BIND_IP=${OBSERVER_PRIVATE_IP}
BUNDLE_PATH=${bundle}
BUNDLE_SHA256=${bundle_sha}
BUNDLE_MANIFEST_SHA256=${manifest_sha}
HOST_COLLECTOR_SHA256=$(sha256_file "${HOST_COLLECTOR}")
REMOTE_BASE=${REMOTE_BASE}
EOF
  plan_sha="$(write_plan_sha "${plan_file}")"

  echo "Plan-only complete."
  echo "Plan file: ${plan_file}"
  echo "Plan sha256: ${plan_sha}"
  echo "Bundle: ${bundle}"
  echo "Bundle sha256: ${bundle_sha}"
  echo "Review the plan, then run apply with PLAN_FILE, EXPECTED_PLAN_SHA256, and APPLY_REVIEWED_WORKLOAD=1."
}

random_capability() {
  require_command openssl
  openssl rand -hex 32
}

remote_prepare_command() {
  local release_dir="$1"
  cat <<EOF
set -euo pipefail
sudo install -d -m 0755 '${REMOTE_BASE}/releases'
sudo rm -rf '${release_dir}'
sudo install -d -m 0755 '${release_dir}'
sudo tar -xzf '${REMOTE_ARCHIVE}' -C '${release_dir}'
sudo ln -sfn '${release_dir}' '${REMOTE_BASE}/current'
sudo chown -R root:root '${release_dir}'
EOF
}

remote_compose_up_command() {
  local release_dir="$1"
  local compose_file="$2"
  cat <<EOF
set -euo pipefail
cd '${release_dir}'
sudo docker compose --env-file .env -f '${compose_file}' up -d --build
sudo docker compose --env-file .env -f '${compose_file}' ps
EOF
}

write_runtime_envs() {
  local dir="$1"
  local action_capability="$2"
  local fault_capability="$3"
  local run_id="p174-live-${BUNDLE_SHA256:0:16}"
  [[ -n "${action_capability}" && -n "${fault_capability}" && "${action_capability}" != "${fault_capability}" ]] \
    || die "missing separated runtime capabilities"
  mkdir -p "${dir}"
  chmod 700 "${dir}"
  cat >"${dir}/target.env" <<EOF
P174_TARGET_BIND_IP=${TARGET_BIND_IP}
P174_PROJECT_ID=${PROJECT_ID}
P174_TARGET_ID=${TARGET_VM}
P174_RUN_ID=${run_id}
P174_POLICY_VERSION=p174-policy-v1
P174_DEPLOYMENT_BUNDLE_SHA256=${BUNDLE_SHA256}
P174_ACTION_CAPABILITY=${action_capability}
P174_FAULT_CAPABILITY=${fault_capability}
EOF
  cat >"${dir}/authority.env" <<EOF
P174_ACTION_CAPABILITY=${action_capability}
P174_FAULT_CAPABILITY=${fault_capability}
P174_PROJECT_ID=${PROJECT_ID}
P174_TARGET_ID=${TARGET_VM}
P174_RUN_ID=${run_id}
P174_POLICY_VERSION=p174-policy-v1
EOF
  cat >"${dir}/observer.env" <<EOF
P174_TARGET_PROMETHEUS_URL=http://${TARGET_BIND_IP}:9090
P174_TARGET_LOKI_URL=http://${TARGET_BIND_IP}:3100
P174_TARGET_API_URL=http://${TARGET_BIND_IP}:8000
P174_SESSION_ID=${run_id}
P174_MANIFEST_SHA256=${BUNDLE_MANIFEST_SHA256}
P174_PROJECT_ID=${PROJECT_ID}
P174_TARGET_ID=${TARGET_VM}
P174_RUN_ID=${run_id}
P174_POLICY_VERSION=p174-policy-v1
P174_DEPLOYMENT_BUNDLE_SHA256=${BUNDLE_SHA256}
EOF
  chmod 600 "${dir}/target.env" "${dir}/authority.env" "${dir}/observer.env"
}

read_env_value() {
  local env_file="$1"
  local wanted="$2"
  local line key value found=""
  [[ -f "${env_file}" ]] || die "missing env file: ${env_file}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -n "${line}" ]] || continue
    [[ "${line}" =~ ^([A-Z0-9_]+)=([A-Za-z0-9._:/=-]+)$ ]] || die "invalid env line in ${env_file}"
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    if [[ "${key}" == "${wanted}" ]]; then
      [[ -z "${found}" ]] || die "duplicate env key: ${wanted}"
      found="${value}"
    fi
  done <"${env_file}"
  [[ -n "${found}" ]] || die "missing env key: ${wanted}"
  printf '%s\n' "${found}"
}

validate_runtime_authority() {
  require_command jq
  local runtime_env="$1"
  local provider_manifest="$2"
  local action_capability fault_capability run_id provider_sha
  [[ -f "${runtime_env}" ]] || die "missing ignored runtime env; run workload apply first"
  [[ -f "${provider_manifest}" ]] || die "missing ignored provider manifest; run workload apply first"
  action_capability="$(read_env_value "${runtime_env}" P174_ACTION_CAPABILITY)"
  fault_capability="$(read_env_value "${runtime_env}" P174_FAULT_CAPABILITY)"
  run_id="$(read_env_value "${runtime_env}" P174_RUN_ID)"
  [[ "${action_capability}" =~ ^[0-9a-f]{64}$ ]] || die "invalid local action capability"
  [[ "${fault_capability}" =~ ^[0-9a-f]{64}$ ]] || die "invalid local fault capability"
  [[ "${action_capability}" != "${fault_capability}" ]] || die "action and fault capabilities must be distinct"
  [[ "$(read_env_value "${runtime_env}" P174_PROJECT_ID)" == "${PROJECT_ID}" ]] || die "runtime project binding mismatch"
  [[ "$(read_env_value "${runtime_env}" P174_TARGET_ID)" == "${TARGET_VM}" ]] || die "runtime target binding mismatch"
  [[ "$(read_env_value "${runtime_env}" P174_POLICY_VERSION)" == "p174-policy-v1" ]] || die "runtime policy binding mismatch"
  [[ "${run_id}" == "p174-live-${BUNDLE_SHA256:0:16}" ]] || die "runtime bundle binding mismatch"
  jq -e \
    --arg project "${PROJECT_ID}" \
    --arg target "${TARGET_VM}" \
    --arg run "${run_id}" \
    --arg zone "${ZONE}" \
    '.schema_version == "p174.live_session_manifest.v1" and
     .project_id == $project and
     .target_id == $target and
     .run_id == $run and
     .zone == $zone and
     .allowed_targets == [$target] and
     (.allowed_actions | sort) == ["restart_worker", "rollback_canary", "tune_pool"] and
     .production_mutation_allowed == false and
     .user_staging_mutation_allowed == false and
     .service_account_keys_allowed == false and
     .live_apply_acknowledged == false' "${provider_manifest}" >/dev/null \
    || die "provider manifest binding or authority flags are invalid"
  provider_sha="$(sha256_file "${provider_manifest}")"
  printf '%s\t%s\t%s\t%s\n' "${action_capability}" "${fault_capability}" "${run_id}" "${provider_sha}"
}

write_p175_harness_manifest() {
  local manifest="$1"
  local reviewer="$2"
  local seed="$3"
  local reviewed_at="$4"
  local observer_contract_hash action_contract_hash
  [[ "${P175_REVIEWED_HARNESS:-0}" == "1" ]] || die "set P175_REVIEWED_HARNESS=1 after reviewing the P175 harness contract"
  [[ "${reviewer}" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]] || die "invalid P175_REVIEWER_ID"
  [[ "${seed}" =~ ^[0-9]+$ ]] && (( seed <= 4294967295 )) || die "P175_SEED must be an integer from 0 to 4294967295"
  observer_contract_hash="sha256:$({ sha256_file "${LAB_DIR}/observer/p174_observer.py"; sha256_file "${REPO_ROOT}/app/services/p174_live_harness.py"; } | shasum -a 256 | awk '{print $1}')"
  action_contract_hash="sha256:$({ sha256_file "${LAB_DIR}/workload/p174_workload.py"; sha256_file "${REPO_ROOT}/app/services/p174_gcp_provider_lab.py"; sha256_file "${REPO_ROOT}/scripts/run_p174_live_harness.py"; } | shasum -a 256 | awk '{print $1}')"
  cat >"${manifest}" <<EOF
{"action_contract_hash":"${action_contract_hash}","allowed_actions":["tune_pool","restart_worker","rollback_canary"],"allowed_targets":["${TARGET_VM}"],"lab_id":"p174-live-lab","manifest_id":"p175-live-harness-${seed}","observer_contract_hash":"${observer_contract_hash}","reviewed":true,"reviewed_at":"${reviewed_at}","reviewed_by":"${reviewer}","schema_version":"p174.live_harness_manifest.v1","seed":${seed}}
EOF
}

make_p175_live_plan() {
  require_command jq
  require_command shasum
  local plan_file expected project runtime_env provider_manifest reviewed_at work_dir harness_manifest p175_plan p175_sha harness_sha runtime_info action_capability fault_capability run_id provider_sha seed reviewer
  plan_file="${PLAN_FILE:?set PLAN_FILE to the reviewed workload deployment plan}"
  expected="${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed workload deployment plan sha256}"
  validate_plan_digest "${plan_file}" "${expected}"
  load_plan "${plan_file}"
  [[ "${PLAN_KIND}" == "workload-deploy" ]] || die "PLAN_FILE is not a workload deployment plan"
  project="$(project_id)"
  runtime_env="${LAB_DIR}/runtime/${project}.env"
  provider_manifest="${LAB_DIR}/runtime/${project}-manifest.json"
  runtime_info="$(validate_runtime_authority "${runtime_env}" "${provider_manifest}")"
  action_capability="$(awk '{print $1}' <<<"${runtime_info}")"
  fault_capability="$(awk '{print $2}' <<<"${runtime_info}")"
  run_id="$(awk '{print $3}' <<<"${runtime_info}")"
  provider_sha="$(awk '{print $4}' <<<"${runtime_info}")"
  reviewed_at="$(timestamp)"
  seed="${P175_SEED:-175174}"
  reviewer="${P175_REVIEWER_ID:?set P175_REVIEWER_ID for the reviewed harness manifest}"
  work_dir="$(new_work_dir)"
  harness_manifest="${work_dir}/p175-live-harness-manifest.json"
  p175_plan="${work_dir}/p175-live-plan.env"
  write_p175_harness_manifest "${harness_manifest}" "${reviewer}" "${seed}" "${reviewed_at}"
  harness_sha="$(sha256_file "${harness_manifest}")"
  cat >"${p175_plan}" <<EOF
PLAN_KIND=p175-live-harness
CREATED_AT=${reviewed_at}
PROJECT_ID=${project}
ZONE=${ZONE}
TARGET_VM=${TARGET_VM}
OBSERVER_VM=${OBSERVER_VM}
WORKLOAD_PLAN_FILE=${plan_file}
WORKLOAD_PLAN_SHA256=${expected}
HARNESS_MANIFEST_PATH=${harness_manifest}
HARNESS_MANIFEST_SHA256=${harness_sha}
PROVIDER_MANIFEST_PATH=${provider_manifest}
PROVIDER_MANIFEST_SHA256=${provider_sha}
ORCHESTRATOR_SHA256=$(sha256_file "${BASH_SOURCE[0]}")
ACTION_ENV_PATH=${runtime_env}
ACTION_CAPABILITY_SHA256=$(printf '%s' "${action_capability}" | shasum -a 256 | awk '{print $1}')
FAULT_CAPABILITY_SHA256=$(printf '%s' "${fault_capability}" | shasum -a 256 | awk '{print $1}')
RUN_ID=${run_id}
TARGET_LOOPBACK_PORT=8020
OBSERVER_LOOPBACK_PORT=8030
EVAL_DIR=${REPO_ROOT}/evals/p174/live/p175-${reviewed_at}
EOF
  p175_sha="$(write_plan_sha "${p175_plan}")"
  echo "P175 live plan-only complete."
  echo "P175 plan file: ${p175_plan}"
  echo "P175 plan sha256: ${p175_sha}"
  echo "Harness manifest: ${harness_manifest}"
  echo "Harness manifest sha256: ${harness_sha}"
  echo "Review the plan and manifest, then run p175-live with P175_PLAN_FILE, EXPECTED_P175_PLAN_SHA256, and EXPECTED_HARNESS_MANIFEST_SHA256."
}

load_p175_plan() {
  local plan_file="$1"
  local line key value seen_keys="|"
  unset PLAN_KIND CREATED_AT PROJECT_ID ZONE TARGET_VM OBSERVER_VM
  unset WORKLOAD_PLAN_FILE WORKLOAD_PLAN_SHA256 HARNESS_MANIFEST_PATH HARNESS_MANIFEST_SHA256
  unset PROVIDER_MANIFEST_PATH PROVIDER_MANIFEST_SHA256 ORCHESTRATOR_SHA256 ACTION_ENV_PATH ACTION_CAPABILITY_SHA256
  unset FAULT_CAPABILITY_SHA256 RUN_ID TARGET_LOOPBACK_PORT OBSERVER_LOOPBACK_PORT EVAL_DIR
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^([A-Z0-9_]+)=([A-Za-z0-9._/:=-]+)$ ]] || die "invalid P175 plan line"
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    case "${key}" in
      PLAN_KIND|CREATED_AT|PROJECT_ID|ZONE|TARGET_VM|OBSERVER_VM|WORKLOAD_PLAN_FILE|WORKLOAD_PLAN_SHA256|HARNESS_MANIFEST_PATH|HARNESS_MANIFEST_SHA256|PROVIDER_MANIFEST_PATH|PROVIDER_MANIFEST_SHA256|ORCHESTRATOR_SHA256|ACTION_ENV_PATH|ACTION_CAPABILITY_SHA256|FAULT_CAPABILITY_SHA256|RUN_ID|TARGET_LOOPBACK_PORT|OBSERVER_LOOPBACK_PORT|EVAL_DIR) ;;
      *) die "unexpected P175 plan key: ${key}" ;;
    esac
    [[ "${seen_keys}" != *"|${key}|"* ]] || die "duplicate P175 plan key: ${key}"
    seen_keys="${seen_keys}${key}|"
    printf -v "${key}" '%s' "${value}"
  done <"${plan_file}"
  : "${PLAN_KIND:?missing PLAN_KIND in P175 plan}"
  : "${PROJECT_ID:?missing PROJECT_ID in P175 plan}"
  : "${ZONE:?missing ZONE in P175 plan}"
  : "${TARGET_VM:?missing TARGET_VM in P175 plan}"
  : "${OBSERVER_VM:?missing OBSERVER_VM in P175 plan}"
  : "${WORKLOAD_PLAN_FILE:?missing WORKLOAD_PLAN_FILE in P175 plan}"
  : "${WORKLOAD_PLAN_SHA256:?missing WORKLOAD_PLAN_SHA256 in P175 plan}"
  : "${HARNESS_MANIFEST_PATH:?missing HARNESS_MANIFEST_PATH in P175 plan}"
  : "${HARNESS_MANIFEST_SHA256:?missing HARNESS_MANIFEST_SHA256 in P175 plan}"
  : "${PROVIDER_MANIFEST_PATH:?missing PROVIDER_MANIFEST_PATH in P175 plan}"
  : "${PROVIDER_MANIFEST_SHA256:?missing PROVIDER_MANIFEST_SHA256 in P175 plan}"
  : "${ORCHESTRATOR_SHA256:?missing ORCHESTRATOR_SHA256 in P175 plan}"
  : "${ACTION_ENV_PATH:?missing ACTION_ENV_PATH in P175 plan}"
  : "${ACTION_CAPABILITY_SHA256:?missing ACTION_CAPABILITY_SHA256 in P175 plan}"
  : "${FAULT_CAPABILITY_SHA256:?missing FAULT_CAPABILITY_SHA256 in P175 plan}"
  : "${RUN_ID:?missing RUN_ID in P175 plan}"
  : "${TARGET_LOOPBACK_PORT:?missing TARGET_LOOPBACK_PORT in P175 plan}"
  : "${OBSERVER_LOOPBACK_PORT:?missing OBSERVER_LOOPBACK_PORT in P175 plan}"
  : "${EVAL_DIR:?missing EVAL_DIR in P175 plan}"
  [[ "${PLAN_KIND}" == "p175-live-harness" ]] || die "P175_PLAN_FILE is not a live harness plan"
  [[ "${PROJECT_ID}" == "$(project_id)" ]] || die "P175 plan project does not match EXPECTED_PROJECT_ID"
  [[ "${ZONE}" == "${ALLOWED_ZONE}" ]] || die "P175 plan zone is not allowed"
  [[ "${TARGET_VM}" == "${TARGET_INSTANCE}" ]] || die "P175 plan target instance is not allowed"
  [[ "${OBSERVER_VM}" == "${OBSERVER_INSTANCE}" ]] || die "P175 plan observer instance is not allowed"
  [[ "${TARGET_LOOPBACK_PORT}" == "8020" ]] || die "P175 target loopback port is not allowed"
  [[ "${OBSERVER_LOOPBACK_PORT}" == "8030" ]] || die "P175 observer loopback port is not allowed"
  [[ "${EVAL_DIR}" == "${REPO_ROOT}/evals/p174/live/p175-"* ]] || die "P175 EVAL_DIR is not allowed"
}

allocate_loopback_port() {
  require_command uv
  uv run --no-sync python -c 'import socket; sock=socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()'
}

start_iap_loopback_tunnel() {
  local instance="$1"
  local local_port="$2"
  local remote_host="$3"
  local remote_port="$4"
  local log_file="$5"
  local pid_var="$6"
  case "${remote_host}" in
    127.0.0.1|10.174.0.10) ;;
    *) die "P175 tunnel remote host is not allowed: ${remote_host}" ;;
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

run_p175_live_harness() {
  require_command curl
  require_command gcloud
  require_command jq
  require_command shasum
  require_command uv
  local p175_plan expected expected_harness runtime_info action_capability fault_capability run_id provider_sha target_local_port observer_local_port target_log observer_log target_pid="" observer_pid="" cleanup_cmd summary_tmp jsonl_tmp summary_out jsonl_out
  local -a max_args diagnostic_args
  max_args=(--max-scenarios 100)
  diagnostic_args=()
  p175_plan="${P175_PLAN_FILE:?set P175_PLAN_FILE to the reviewed P175 live plan}"
  expected="${EXPECTED_P175_PLAN_SHA256:?set EXPECTED_P175_PLAN_SHA256 to the reviewed P175 live plan sha256}"
  expected_harness="${EXPECTED_HARNESS_MANIFEST_SHA256:?set EXPECTED_HARNESS_MANIFEST_SHA256 to the reviewed harness manifest sha256}"
  validate_plan_digest "${p175_plan}" "${expected}"
  load_p175_plan "${p175_plan}"
  [[ "${expected_harness}" == "${HARNESS_MANIFEST_SHA256}" ]] || die "reviewed harness manifest sha mismatch with P175 plan"
  validate_plan_digest "${WORKLOAD_PLAN_FILE}" "${WORKLOAD_PLAN_SHA256}"
  load_plan "${WORKLOAD_PLAN_FILE}"
  [[ "${PLAN_KIND}" == "workload-deploy" ]] || die "P175 workload plan is not a deployment plan"
  [[ "$(sha256_file "${HARNESS_MANIFEST_PATH}")" == "${HARNESS_MANIFEST_SHA256}" ]] || die "harness manifest digest mismatch"
  [[ "$(sha256_file "${PROVIDER_MANIFEST_PATH}")" == "${PROVIDER_MANIFEST_SHA256}" ]] || die "provider manifest digest mismatch"
  [[ "$(sha256_file "${BASH_SOURCE[0]}")" == "${ORCHESTRATOR_SHA256}" ]] || die "P175 orchestrator digest mismatch"
  runtime_info="$(validate_runtime_authority "${ACTION_ENV_PATH}" "${PROVIDER_MANIFEST_PATH}")"
  action_capability="$(awk '{print $1}' <<<"${runtime_info}")"
  fault_capability="$(awk '{print $2}' <<<"${runtime_info}")"
  run_id="$(awk '{print $3}' <<<"${runtime_info}")"
  provider_sha="$(awk '{print $4}' <<<"${runtime_info}")"
  [[ "${run_id}" == "${RUN_ID}" ]] || die "P175 run binding mismatch"
  [[ "${provider_sha}" == "${PROVIDER_MANIFEST_SHA256}" ]] || die "P175 provider manifest binding changed"
  [[ "$(printf '%s' "${action_capability}" | shasum -a 256 | awk '{print $1}')" == "${ACTION_CAPABILITY_SHA256}" ]] || die "action capability digest mismatch"
  [[ "$(printf '%s' "${fault_capability}" | shasum -a 256 | awk '{print $1}')" == "${FAULT_CAPABILITY_SHA256}" ]] || die "fault capability digest mismatch"
  [[ "${action_capability}" != "${fault_capability}" ]] || die "action and fault capabilities must be distinct"

  target_local_port="$(allocate_loopback_port)"
  observer_local_port="$(allocate_loopback_port)"
  [[ "${target_local_port}" =~ ^[0-9]+$ && "${observer_local_port}" =~ ^[0-9]+$ && "${target_local_port}" != "${observer_local_port}" ]] \
    || die "failed to allocate distinct local tunnel ports"
  target_log="$(mktemp "${TMPDIR:-/tmp}/p175-target-iap-tunnel.XXXXXX")"
  observer_log="$(mktemp "${TMPDIR:-/tmp}/p175-observer-iap-tunnel.XXXXXX")"
  start_iap_loopback_tunnel "${TARGET_VM}" "${target_local_port}" "${TARGET_BIND_IP}" "${TARGET_LOOPBACK_PORT}" "${target_log}" target_pid
  printf -v cleanup_cmd 'kill %q 2>/dev/null || true; wait %q 2>/dev/null || true; rm -f -- %q %q' "${target_pid}" "${target_pid}" "${target_log}" "${observer_log}"
  trap "${cleanup_cmd}" EXIT
  start_iap_loopback_tunnel "${OBSERVER_VM}" "${observer_local_port}" "127.0.0.1" "${OBSERVER_LOOPBACK_PORT}" "${observer_log}" observer_pid
  printf -v cleanup_cmd 'kill %q %q 2>/dev/null || true; wait %q %q 2>/dev/null || true; rm -f -- %q %q' "${target_pid}" "${observer_pid}" "${target_pid}" "${observer_pid}" "${target_log}" "${observer_log}"
  trap "${cleanup_cmd}" EXIT
  wait_loopback_ready "${target_pid}" "${target_log}" "http://127.0.0.1:${target_local_port}/health" "target"
  wait_loopback_ready "${target_pid}" "${target_log}" "http://127.0.0.1:${target_local_port}/state" "target"
  wait_loopback_ready "${observer_pid}" "${observer_log}" "http://127.0.0.1:${observer_local_port}/health" "observer"

  mkdir -p "${EVAL_DIR}"
  summary_tmp="${EVAL_DIR}/p175-live-summary.json.tmp"
  jsonl_tmp="${EVAL_DIR}/p175-live-evidence.jsonl.tmp"
  summary_out="${EVAL_DIR}/p175-live-summary.json"
  jsonl_out="${EVAL_DIR}/p175-live-evidence.jsonl"
  if [[ -n "${P175_MAX_SCENARIOS:-}" ]]; then
    [[ "${P175_MAX_SCENARIOS}" =~ ^[0-9]+$ ]] || die "P175_MAX_SCENARIOS must be numeric"
    max_args=(--max-scenarios "${P175_MAX_SCENARIOS}")
  fi
  if [[ "${P175_DIAGNOSTIC_CAMPAIGN_ONLY:-0}" == 1 ]]; then
    diagnostic_args=(--diagnostic-campaign-only)
  elif [[ "${P175_DIAGNOSTIC_CAMPAIGN_ONLY:-0}" != 0 ]]; then
    die "P175_DIAGNOSTIC_CAMPAIGN_ONLY must be 0 or 1"
  fi
  (
    cd "${REPO_ROOT}"
    UV_CACHE_DIR="${TMPDIR:-/tmp}/uv-cache" \
      uv run --no-sync --extra dev python scripts/run_p174_live_harness.py \
        --allow-live-lab \
        --manifest "${HARNESS_MANIFEST_PATH}" \
        --provider-manifest "${PROVIDER_MANIFEST_PATH}" \
        --observer-endpoint "http://127.0.0.1:${observer_local_port}" \
        --action-endpoint "http://127.0.0.1:${target_local_port}" \
        --authority-file "${ACTION_ENV_PATH}" \
        --output-summary "${summary_tmp}" \
        --output-jsonl "${jsonl_tmp}" \
        ${diagnostic_args[@]+"${diagnostic_args[@]}"} \
        "${max_args[@]}"
  )
  [[ -s "${summary_tmp}" && -s "${jsonl_tmp}" ]] || die "P175 live harness did not produce summary and jsonl"
  mv -f "${summary_tmp}" "${summary_out}"
  mv -f "${jsonl_tmp}" "${jsonl_out}"
  if [[ "${P175_DIAGNOSTIC_CAMPAIGN_ONLY:-0}" == 1 ]]; then
    jq -e '.qualified == false and .diagnostic_campaign_only == true and .status == "diagnostic_complete" and .gates.healthy_window.passed == false and .gates.scenario_campaign.passed == true' "${summary_out}" >/dev/null \
      || die "P175 diagnostic campaign did not pass; preserved ${summary_out} and ${jsonl_out}"
  else
    jq -e '.qualified == true and .diagnostic_campaign_only == false and .status == "qualified" and .gates.healthy_window.passed == true and .gates.scenario_campaign.passed == true' "${summary_out}" >/dev/null \
      || die "P175 live harness did not qualify; preserved ${summary_out} and ${jsonl_out}"
  fi
  kill "${target_pid}" "${observer_pid}" 2>/dev/null || true
  wait "${target_pid}" "${observer_pid}" 2>/dev/null || true
  rm -f -- "${target_log}" "${observer_log}"
  trap - EXIT
  echo "P175 live harness completed. Summary: ${summary_out} Evidence: ${jsonl_out}"
}

install_env_command() {
  local release_dir="$1"
  cat <<EOF
set -euo pipefail
sudo install -m 0600 /tmp/p174-runtime.env '${release_dir}/.env'
rm -f /tmp/p174-runtime.env
EOF
}

install_observer_host_collector() {
  gcloud_scp_to "${HOST_COLLECTOR}" "${OBSERVER_VM}" "/tmp/observer-host-evidence-collector.sh"
  gcloud_ssh "${OBSERVER_VM}" "set -euo pipefail
for unit in opscat-p174-observer-evidence.timer opscat-p174-observer-evidence.service; do
  load_state=\$(sudo systemctl show --property=LoadState --value \"\${unit}\")
  if [[ \"\${load_state}\" == not-found ]]; then continue; fi
  sudo systemctl stop \"\${unit}\"
  active_state=\$(sudo systemctl show --property=ActiveState --value \"\${unit}\")
  [[ \"\${active_state}\" == inactive ]] || { echo \"collector unit not inactive: \${unit}:\${active_state}\" >&2; exit 1; }
done
sudo install -d -m 0755 /usr/local/lib/opscat-p174
sudo install -m 0755 /tmp/observer-host-evidence-collector.sh /usr/local/lib/opscat-p174/observer-host-evidence-collector.sh
rm -f /tmp/observer-host-evidence-collector.sh
sudo install -d -m 0750 -o root -g root /var/lib/opscat-p174/evidence
sudo install -d -m 0750 -o root -g root /var/lib/opscat-p174/evidence/history
if sudo test -s /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl; then
  sudo cp --preserve=timestamps /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl \
    \"/var/lib/opscat-p174/evidence/history/compute-target-evidence-predeploy-\$(date -u +%Y%m%dT%H%M%SZ).jsonl\"
fi
sudo truncate -s 0 /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl
sudo chmod 0600 /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl
sudo install -d -m 0755 /etc/opscat-p174
sudo tee /etc/opscat-p174/observer-evidence.env >/dev/null <<'ENV'
P174_PROJECT_ID=${PROJECT_ID}
P174_ZONE=${ZONE}
P174_TARGET_INSTANCE=${TARGET_VM}
P174_EVIDENCE_DIR=/var/lib/opscat-p174/evidence
ENV
sudo chmod 0600 /etc/opscat-p174/observer-evidence.env
sudo tee /etc/systemd/system/opscat-p174-observer-evidence.service >/dev/null <<'UNIT'
[Unit]
Description=Collect bounded P174 target Compute Engine evidence from observer host
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/opscat-p174/observer-evidence.env
ExecStart=/usr/local/lib/opscat-p174/observer-host-evidence-collector.sh
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/opscat-p174/evidence /run
UNIT
sudo tee /etc/systemd/system/opscat-p174-observer-evidence.timer >/dev/null <<'UNIT'
[Unit]
Description=Run P174 observer host evidence collection every minute

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=10s
Persistent=true

[Install]
WantedBy=timers.target
UNIT
sudo tee /etc/systemd/system/opscat-p174-container-metadata-block.service >/dev/null <<'UNIT'
[Unit]
Description=Block Docker containers from reaching the GCE metadata server
After=docker.service
Wants=docker.service

[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/bin/sh -c 'iptables -C DOCKER-USER -d 169.254.169.254/32 -j REJECT 2>/dev/null || iptables -I DOCKER-USER 1 -d 169.254.169.254/32 -j REJECT'
ExecStop=/bin/sh -c 'while iptables -C DOCKER-USER -d 169.254.169.254/32 -j REJECT 2>/dev/null; do iptables -D DOCKER-USER -d 169.254.169.254/32 -j REJECT; done'

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now opscat-p174-container-metadata-block.service
sudo systemctl enable --now opscat-p174-observer-evidence.timer
sudo systemctl start opscat-p174-observer-evidence.service
sudo test -s /var/lib/opscat-p174/evidence/compute-target-evidence.jsonl"
}

verify_target_health() {
  gcloud_ssh "${TARGET_VM}" "set -euo pipefail
for url in \
  'http://${TARGET_BIND_IP}:8000/health' \
  'http://${TARGET_BIND_IP}:8020/health' \
  'http://${TARGET_BIND_IP}:9090/-/ready' \
  'http://${TARGET_BIND_IP}:3100/ready'
do
  for attempt in \$(seq 1 30); do
    if curl -fsS --max-time 3 \"\${url}\" >/dev/null; then
      echo \"healthy \${url}\"
      break
    fi
    if [[ \"\${attempt}\" == 30 ]]; then
      echo \"health check failed: \${url}\" >&2
      exit 1
    fi
    sleep 5
  done
done"
}

verify_observer_health() {
  local release_dir="$1"
  gcloud_ssh "${OBSERVER_VM}" "set -euo pipefail
cd '${release_dir}'
for attempt in \$(seq 1 30); do
  if sudo docker compose --env-file .env -f docker-compose.observer.yml exec -T observer python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8030/health', timeout=3).read()\" >/dev/null; then
    echo 'healthy observer'
    exit 0
  fi
  sleep 5
done
echo 'observer health check failed' >&2
sudo docker compose --env-file .env -f docker-compose.observer.yml ps >&2
exit 1"
}

collect_evidence() {
  local evidence_dir release_dir remote_evidence remote_tar compute_evidence_dir collect_health incident_evidence_safe
  evidence_dir="${EVIDENCE_DIR:-${REPO_ROOT}/evals/p174/live/$(timestamp)}"
  release_dir="${REMOTE_BASE}/current"
  remote_evidence="/tmp/p174-evidence-$(timestamp)"
  remote_tar="${remote_evidence}.tgz"
  mkdir -p "${evidence_dir}"

  gcloud_ssh "${TARGET_VM}" "set -euo pipefail
rm -rf '${remote_evidence}'
mkdir -p '${remote_evidence}/target'
cd '${release_dir}'
sudo docker compose --env-file .env -f docker-compose.target.yml ps >'${remote_evidence}/target/docker-compose-ps.txt'
sudo docker compose --env-file .env -f docker-compose.target.yml logs --no-color --tail=200 >'${remote_evidence}/target/docker-compose-logs.txt'
curl -fsS --max-time 5 'http://${TARGET_BIND_IP}:8000/health' >'${remote_evidence}/target/api-health.json'
curl -fsS --max-time 5 'http://${TARGET_BIND_IP}:8020/health' >'${remote_evidence}/target/fault-controller-health.json'
curl -fsS --max-time 5 'http://${TARGET_BIND_IP}:8020/state' >'${remote_evidence}/target/fault-controller-state.json'
curl -fsS --max-time 5 'http://${TARGET_BIND_IP}:9090/-/ready' >'${remote_evidence}/target/prometheus-ready.txt'
curl -fsS --max-time 5 'http://${TARGET_BIND_IP}:3100/ready' >'${remote_evidence}/target/loki-ready.txt'
tar -C '${remote_evidence}' -czf '${remote_tar}' target"
  gcloud_scp_from "${TARGET_VM}" "${remote_tar}" "${evidence_dir}/target-evidence.tgz"

  gcloud_ssh "${OBSERVER_VM}" "set -euo pipefail
rm -rf '${remote_evidence}'
mkdir -p '${remote_evidence}/observer'
cd '${release_dir}'
sudo docker compose --env-file .env -f docker-compose.observer.yml ps >'${remote_evidence}/observer/docker-compose-ps.txt'
sudo docker compose --env-file .env -f docker-compose.observer.yml logs --no-color --tail=200 >'${remote_evidence}/observer/docker-compose-logs.txt'
sudo docker compose --env-file .env -f docker-compose.observer.yml exec -T observer python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8030/collect', timeout=10).read().decode())\" >'${remote_evidence}/observer/collect.json'
sudo docker compose --env-file .env -f docker-compose.observer.yml exec -T observer sh -c 'cat /var/lib/p174-observer/receipts.jsonl 2>/dev/null || true' >'${remote_evidence}/observer/receipts.jsonl'
sudo docker compose --env-file .env -f docker-compose.observer.yml exec -T evaluator sh -c 'cat /var/lib/p174-observer/evaluations.jsonl 2>/dev/null || true' >'${remote_evidence}/observer/evaluations.jsonl'
collector_timer_was_active=0
collector_timer_state=\$(sudo systemctl show --property=ActiveState --value opscat-p174-observer-evidence.timer)
case \"\${collector_timer_state}\" in
  active) collector_timer_was_active=1 ;;
  inactive) ;;
  *) echo \"unexpected collector timer state: \${collector_timer_state}\" >&2; exit 1 ;;
esac
restore_collector_timer() {
  if [[ \"\${collector_timer_was_active}\" == 1 ]]; then sudo systemctl start opscat-p174-observer-evidence.timer; fi
}
trap restore_collector_timer EXIT
if [[ \"\${collector_timer_was_active}\" == 1 ]]; then
  sudo systemctl stop opscat-p174-observer-evidence.timer
fi
collector_service_state=\$(sudo systemctl show --property=ActiveState --value opscat-p174-observer-evidence.service)
case \"\${collector_service_state}\" in
  active) sudo systemctl stop opscat-p174-observer-evidence.service ;;
  inactive) ;;
  *) echo \"unexpected collector service state: \${collector_service_state}\" >&2; exit 1 ;;
esac
collector_timer_state=\$(sudo systemctl show --property=ActiveState --value opscat-p174-observer-evidence.timer)
collector_service_state=\$(sudo systemctl show --property=ActiveState --value opscat-p174-observer-evidence.service)
[[ \"\${collector_timer_state}\" == inactive ]] || { echo \"collector timer not inactive during evidence snapshot: \${collector_timer_state}\" >&2; exit 1; }
[[ \"\${collector_service_state}\" == inactive ]] || { echo \"collector service not inactive during evidence snapshot: \${collector_service_state}\" >&2; exit 1; }
sudo tar -C /var/lib/opscat-p174 -czf '${remote_evidence}/observer/host-compute-evidence.tgz' evidence
restore_collector_timer
trap - EXIT
tar -C '${remote_evidence}' -czf '${remote_tar}' observer"
  gcloud_scp_from "${OBSERVER_VM}" "${remote_tar}" "${evidence_dir}/observer-evidence.tgz"

  for required in \
    target/docker-compose-ps.txt \
    target/api-health.json \
    target/fault-controller-state.json \
    target/prometheus-ready.txt \
    target/loki-ready.txt
  do
    tar -tzf "${evidence_dir}/target-evidence.tgz" | awk -v required="${required}" '$0 == required { found = 1 } END { exit !found }' || die "target evidence missing ${required}"
  done
  for required in \
    observer/docker-compose-ps.txt \
    observer/collect.json \
    observer/receipts.jsonl \
    observer/evaluations.jsonl \
    observer/host-compute-evidence.tgz
  do
    tar -tzf "${evidence_dir}/observer-evidence.tgz" | awk -v required="${required}" '$0 == required { found = 1 } END { exit !found }' || die "observer evidence missing ${required}"
  done
  tar -xOzf "${evidence_dir}/observer-evidence.tgz" observer/receipts.jsonl | awk 'NF { found = 1 } END { exit !found }' || die "observer receipt chain is empty"
  tar -xOzf "${evidence_dir}/observer-evidence.tgz" observer/evaluations.jsonl | awk 'NF { found = 1 } END { exit !found }' || die "observer evaluation history is empty"
  compute_evidence_dir="$(mktemp -d "${TMPDIR:-/tmp}/p174-compute-evidence.XXXXXX")"
  tar -xOzf "${evidence_dir}/observer-evidence.tgz" observer/host-compute-evidence.tgz >"${compute_evidence_dir}/host-compute-evidence.tgz"
  tar -xOzf "${compute_evidence_dir}/host-compute-evidence.tgz" evidence/compute-target-evidence.jsonl >"${compute_evidence_dir}/compute-target-evidence.jsonl" \
    || { rm -rf -- "${compute_evidence_dir}"; die "host compute evidence is missing compute-target-evidence.jsonl"; }
  jq -e -s \
    --arg project "${PROJECT_ID}" \
    --arg target "${TARGET_VM}" \
    --arg zone "${ZONE}" \
    'length > 0 and all(.[ ];
      .schema_version == "p174.host_compute_evidence.v1" and
      .project_id == $project and
      .self_link_project == $project and
      .http_status == 200 and
      .resource.name == $target and
      .resource.zone == $zone and
      .resource.status == "RUNNING"
    )' "${compute_evidence_dir}/compute-target-evidence.jsonl" >/dev/null \
    || { rm -rf -- "${compute_evidence_dir}"; die "host compute evidence does not prove the reviewed running target"; }
  rm -rf -- "${compute_evidence_dir}"
  collect_health="$(tar -xOzf "${evidence_dir}/observer-evidence.tgz" observer/collect.json | jq -er '.evaluation.healthy | if type == "boolean" then tostring else error("healthy_not_boolean") end')" || die "observer collect evidence is invalid"
  if [[ "${collect_health}" != "true" ]]; then
    incident_evidence_safe="$(
      tar -xOzf "${evidence_dir}/observer-evidence.tgz" observer/collect.json \
        | jq -er '(.evaluation.signals.prometheus == true and
                    .evaluation.signals.loki == true and
                    .evaluation.signals.api == false and
                    (.evaluation.failures | sort) == ["health_signal_failed:api"]) | tostring'
    )" || die "observer incident evidence is invalid"
    if [[ "${ALLOW_UNHEALTHY_EVIDENCE:-0}" != "1" || "${incident_evidence_safe}" != "true" ]]; then
      die "observer evidence is not a safely observed API incident"
    fi
  fi

  cat >"${evidence_dir}/README.md" <<EOF
# P174 workload evidence

- Project: ${PROJECT_ID}
- Zone: ${ZONE}
- Target VM: ${TARGET_VM}
- Observer VM: ${OBSERVER_VM}
- Target private bind IP: ${TARGET_BIND_IP}
- Bundle sha256: ${BUNDLE_SHA256:-not-from-plan}
- Retrieved at: $(timestamp)

Archives:
- target-evidence.tgz
- observer-evidence.tgz
EOF
  echo "Evidence validated and retrieved to ${evidence_dir} (operational_healthy=${collect_health})"
}

apply_workload() {
  require_command gcloud
  require_command shasum
  local plan_file expected plan_project release_dir runtime_dir action_capability fault_capability cleanup_cmd
  plan_file="${PLAN_FILE:?set PLAN_FILE to the reviewed workload plan}"
  expected="${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed workload plan sha256}"
  [[ "${APPLY_REVIEWED_WORKLOAD:-0}" == "1" ]] || die "set APPLY_REVIEWED_WORKLOAD=1 after reviewing the workload plan"
  validate_plan_digest "${plan_file}" "${expected}"
  load_plan "${plan_file}"
  [[ "${PLAN_KIND}" == "workload-deploy" ]] || die "PLAN_FILE is not a workload deployment plan"
  [[ -f "${BUNDLE_PATH}" ]] || die "missing bundle: ${BUNDLE_PATH}"
  [[ "$(sha256_file "${BUNDLE_PATH}")" == "${BUNDLE_SHA256}" ]] || die "bundle digest mismatch"
  [[ "$(sha256_file "${HOST_COLLECTOR}")" == "${HOST_COLLECTOR_SHA256}" ]] || die "observer host collector digest mismatch"

  plan_project="$(project_id)"
  release_dir="${REMOTE_BASE}/releases/${BUNDLE_SHA256}"
  runtime_dir="$(mktemp -d "${TMPDIR:-/tmp}/p174-runtime.XXXXXX")"
  printf -v cleanup_cmd 'rm -rf -- %q' "${runtime_dir}"
  trap "${cleanup_cmd}" EXIT
  action_capability="$(random_capability)"
  fault_capability="$(random_capability)"
  write_runtime_envs "${runtime_dir}" "${action_capability}" "${fault_capability}"
  install -d -m 0700 "${LAB_DIR}/runtime"
  install -m 0600 "${runtime_dir}/authority.env" "${LAB_DIR}/runtime/${plan_project}.env"
  cat >"${LAB_DIR}/runtime/${plan_project}-manifest.json" <<EOF
{
  "schema_version": "p174.live_session_manifest.v1",
  "organization_id": "${P174_ORGANIZATION_ID:?set P174_ORGANIZATION_ID from local-only runtime configuration}",
  "billing_account_id": "${P174_BILLING_ACCOUNT_ID:?set P174_BILLING_ACCOUNT_ID from local-only runtime configuration}",
  "project_id": "${plan_project}",
  "target_id": "${TARGET_VM}",
  "run_id": "p174-live-${BUNDLE_SHA256:0:16}",
  "zone": "${ZONE}",
  "allowed_actions": ["tune_pool", "restart_worker", "rollback_canary"],
  "allowed_targets": ["${TARGET_VM}"],
  "forbidden_project_ids": [${P174_FORBIDDEN_PROJECT_IDS_JSON:-}],
  "lease_ttl_seconds": 300,
  "deadman_seconds": 120,
  "kill_switch": false,
  "dry_run": false,
  "production_mutation_allowed": false,
  "user_staging_mutation_allowed": false,
  "service_account_keys_allowed": false,
  "live_apply_acknowledged": false
}
EOF
  chmod 0600 "${LAB_DIR}/runtime/${plan_project}-manifest.json"

  echo "Copying pinned bundle to ${TARGET_VM} and ${OBSERVER_VM} through IAP."
  gcloud_scp_to "${BUNDLE_PATH}" "${TARGET_VM}" "${REMOTE_ARCHIVE}"
  gcloud_scp_to "${BUNDLE_PATH}" "${OBSERVER_VM}" "${REMOTE_ARCHIVE}"

  echo "Preparing release directories."
  gcloud_ssh "${TARGET_VM}" "$(remote_prepare_command "${release_dir}")"
  gcloud_ssh "${OBSERVER_VM}" "$(remote_prepare_command "${release_dir}")"

  echo "Installing runtime env files without committing secret material."
  gcloud_scp_to "${runtime_dir}/target.env" "${TARGET_VM}" "/tmp/p174-runtime.env"
  gcloud_scp_to "${runtime_dir}/observer.env" "${OBSERVER_VM}" "/tmp/p174-runtime.env"
  gcloud_ssh "${TARGET_VM}" "$(install_env_command "${release_dir}")"
  gcloud_ssh "${OBSERVER_VM}" "$(install_env_command "${release_dir}")"

  echo "Installing observer host evidence collector and Docker metadata block."
  install_observer_host_collector

  echo "Starting target workload."
  gcloud_ssh "${TARGET_VM}" "$(remote_compose_up_command "${release_dir}" "docker-compose.target.yml")"
  verify_target_health

  echo "Starting observer workload."
  gcloud_ssh "${OBSERVER_VM}" "$(remote_compose_up_command "${release_dir}" "docker-compose.observer.yml")"
  verify_observer_health "${release_dir}"

  ALLOW_UNHEALTHY_EVIDENCE=1 PROJECT_ID="${plan_project}" collect_evidence
  rm -rf -- "${runtime_dir}"
  trap - EXIT
}

run_typed_action() {
  require_command gcloud
  require_command curl
  require_command uv
  local dry_run="$1" plan_file runtime_env manifest action request_id tunnel_log tunnel_pid receipt_log cleanup_cmd local_port action_evidence_dir evidence_hash pool_size
  plan_file="${PLAN_FILE:?set PLAN_FILE to the reviewed workload plan}"
  validate_plan_digest "${plan_file}" "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed workload plan sha256}"
  load_plan "${plan_file}"
  [[ "${PLAN_KIND}" == "workload-deploy" ]] || die "PLAN_FILE is not a workload deployment plan"
  action="${P174_ACTION:?set P174_ACTION}"
  case "${action}" in tune_pool|restart_worker|rollback_canary) ;; *) die "unsupported P174_ACTION: ${action}" ;; esac
  request_id="${P174_REQUEST_ID:?set unique P174_REQUEST_ID}"
  [[ "${request_id}" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]] || die "invalid P174_REQUEST_ID"
  pool_size="${P174_POOL_SIZE:-16}"
  [[ "${pool_size}" =~ ^[0-9]+$ ]] && (( pool_size >= 1 && pool_size <= 64 )) || die "P174_POOL_SIZE must be an integer from 1 to 64"
  if [[ "${dry_run}" != "1" && "${APPLY_REVIEWED_ACTION:-0}" != "1" ]]; then
    die "set APPLY_REVIEWED_ACTION=1 for a live typed action"
  fi
  runtime_env="${LAB_DIR}/runtime/${PROJECT_ID}.env"
  manifest="${LAB_DIR}/runtime/${PROJECT_ID}-manifest.json"
  [[ -f "${runtime_env}" && -f "${manifest}" ]] || die "missing ignored runtime authority files; run workload apply first"
  # shellcheck disable=SC1090
  source "${runtime_env}"
  [[ "${P174_PROJECT_ID}" == "${PROJECT_ID}" && "${P174_TARGET_ID}" == "${TARGET_VM}" ]] || die "runtime binding mismatch"
  action_evidence_dir="${REPO_ROOT}/evals/p174/live/action-input-$(timestamp)-${request_id}"
  ALLOW_UNHEALTHY_EVIDENCE=1 EVIDENCE_DIR="${action_evidence_dir}" collect_evidence
  evidence_hash="sha256:$({ sha256_file "${action_evidence_dir}/target-evidence.tgz"; sha256_file "${action_evidence_dir}/observer-evidence.tgz"; } | shasum -a 256 | awk '{print $1}')"
  local_port="$(uv run --no-sync python -c 'import socket; sock=socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()')"
  [[ "${local_port}" =~ ^[0-9]+$ ]] || die "failed to allocate a local tunnel port"
  tunnel_log="$(mktemp "${TMPDIR:-/tmp}/p174-iap-tunnel.XXXXXX")"
  gcloud compute ssh "${TARGET_VM}" \
    --project "${PROJECT_ID}" \
    --zone "${ZONE}" \
    --tunnel-through-iap \
    -- -N -o ExitOnForwardFailure=yes \
    -L "127.0.0.1:${local_port}:${TARGET_BIND_IP}:8020" >"${tunnel_log}" 2>&1 &
  tunnel_pid=$!
  printf -v cleanup_cmd 'kill %q 2>/dev/null || true; rm -f -- %q' "${tunnel_pid}" "${tunnel_log}"
  trap "${cleanup_cmd}" EXIT
  for _attempt in $(seq 1 30); do
    if ! kill -0 "${tunnel_pid}" 2>/dev/null; then
      cat "${tunnel_log}" >&2
      die "IAP SSH action tunnel exited before readiness"
    fi
    if curl -fsS --max-time 2 "http://127.0.0.1:${local_port}/state" >/dev/null; then break; fi
    sleep 1
  done
  curl -fsS --max-time 2 "http://127.0.0.1:${local_port}/state" >/dev/null || die "IAP action tunnel did not become ready"
  receipt_log="${REPO_ROOT}/evals/p174/live/provider-receipts.jsonl"
  mkdir -p "$(dirname "${receipt_log}")"
  local runner_args=(
    --manifest "${manifest}"
    --owner-id p174-action-controller
    --action "${action}"
    --request-id "${request_id}"
    --transport http
    --action-endpoint "http://127.0.0.1:${local_port}"
    --evidence-hash "${evidence_hash}"
    --pool-size "${pool_size}"
    --receipt-log "${receipt_log}"
  )
  if [[ "${dry_run}" == "1" ]]; then runner_args+=(--dry-run); else runner_args+=(--allow-live-lab); fi
  (
    cd "${REPO_ROOT}"
    P174_ACTION_CAPABILITY="${P174_ACTION_CAPABILITY}" UV_CACHE_DIR="${TMPDIR:-/tmp}/uv-cache" \
      uv run --no-sync --extra dev python scripts/run_p174_provider_lab.py "${runner_args[@]}"
  )
  kill "${tunnel_pid}" 2>/dev/null || true
  wait "${tunnel_pid}" 2>/dev/null || true
  rm -f -- "${tunnel_log}"
  trap - EXIT
}

evidence_only() {
  require_command gcloud
  local plan_file
  plan_file="${PLAN_FILE:?set PLAN_FILE to the reviewed workload plan}"
  validate_plan_digest "${plan_file}" "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed workload plan sha256}"
  load_plan "${plan_file}"
  [[ "${PLAN_KIND}" == "workload-deploy" ]] || die "PLAN_FILE is not a workload deployment plan"
  collect_evidence
}

teardown_plan() {
  local project created work_dir plan_file plan_sha
  project="$(project_id)"
  created="$(timestamp)"
  work_dir="$(new_work_dir)"
  plan_file="${work_dir}/workload-teardown-plan.env"
  cat >"${plan_file}" <<EOF
PLAN_KIND=workload-teardown
CREATED_AT=${created}
PROJECT_ID=${project}
ZONE=${ALLOWED_ZONE}
TARGET_VM=${TARGET_INSTANCE}
OBSERVER_VM=${OBSERVER_INSTANCE}
TARGET_BIND_IP=${TARGET_PRIVATE_IP}
OBSERVER_BIND_IP=${OBSERVER_PRIVATE_IP}
REMOTE_BASE=${REMOTE_BASE}
EOF
  plan_sha="$(write_plan_sha "${plan_file}")"
  echo "Teardown plan-only complete."
  echo "Plan file: ${plan_file}"
  echo "Plan sha256: ${plan_sha}"
  echo "Review the plan, then run teardown-apply with PLAN_FILE, EXPECTED_PLAN_SHA256, and APPLY_REVIEWED_WORKLOAD_TEARDOWN=1."
}

teardown_apply() {
  require_command gcloud
  local plan_file expected remove_volumes purge_remote_evidence exported_evidence_dir purge_remote_command
  plan_file="${PLAN_FILE:?set PLAN_FILE to the reviewed teardown plan}"
  expected="${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed teardown plan sha256}"
  [[ "${APPLY_REVIEWED_WORKLOAD_TEARDOWN:-0}" == "1" ]] || die "set APPLY_REVIEWED_WORKLOAD_TEARDOWN=1 after reviewing the teardown plan"
  validate_plan_digest "${plan_file}" "${expected}"
  load_plan "${plan_file}"
  [[ "${PLAN_KIND}" == "workload-teardown" ]] || die "PLAN_FILE is not a workload teardown plan"
  remove_volumes=""
  if [[ "${P174_TEARDOWN_VOLUMES:-0}" == "1" ]]; then
    remove_volumes=" --volumes"
  fi
  purge_remote_evidence="${P174_PURGE_REMOTE_EVIDENCE:-0}"
  exported_evidence_dir="${P174_EXPORTED_EVIDENCE_DIR:-}"
  purge_remote_command=""
  if [[ "${purge_remote_evidence}" == "1" ]]; then
    [[ "${P174_TEARDOWN_VOLUMES:-0}" == "1" ]] || die "remote evidence purge requires P174_TEARDOWN_VOLUMES=1"
    [[ -d "${exported_evidence_dir}" ]] || die "remote evidence purge requires P174_EXPORTED_EVIDENCE_DIR"
    [[ -s "${exported_evidence_dir}/target-evidence.tgz" && -s "${exported_evidence_dir}/observer-evidence.tgz" ]] \
      || die "remote evidence purge requires exported target and observer archives"
    purge_remote_command="sudo rm -rf /var/lib/opscat-p174"
  fi

  gcloud_ssh "${OBSERVER_VM}" "set -euo pipefail
if [[ -d '${REMOTE_BASE}/current' ]]; then
  cd '${REMOTE_BASE}/current'
  sudo docker compose --env-file .env -f docker-compose.observer.yml down --remove-orphans${remove_volumes}
fi
sudo systemctl disable --now opscat-p174-observer-evidence.timer 2>/dev/null || true
sudo systemctl disable --now opscat-p174-container-metadata-block.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/opscat-p174-observer-evidence.timer /etc/systemd/system/opscat-p174-observer-evidence.service
sudo rm -f /etc/systemd/system/opscat-p174-container-metadata-block.service
sudo rm -rf /usr/local/lib/opscat-p174 /etc/opscat-p174 '${REMOTE_BASE}' '${REMOTE_ARCHIVE}'
${purge_remote_command}
sudo systemctl daemon-reload"
  gcloud_ssh "${TARGET_VM}" "set -euo pipefail
if [[ -d '${REMOTE_BASE}/current' ]]; then
  cd '${REMOTE_BASE}/current'
  sudo docker compose --env-file .env -f docker-compose.target.yml down --remove-orphans${remove_volumes}
fi
sudo rm -rf '${REMOTE_BASE}' '${REMOTE_ARCHIVE}'"
  rm -f \
    "${LAB_DIR}/runtime/${PROJECT_ID}.env" \
    "${LAB_DIR}/runtime/${PROJECT_ID}-manifest.json"
  echo "Workload teardown complete for ${PROJECT_ID}. Terraform resources were not changed. Remote evidence purge=${purge_remote_evidence}."
}

main() {
  local command_name="${1:-}"
  case "${command_name}" in
    plan)
      make_bundle_plan
      ;;
    apply)
      apply_workload
      ;;
    evidence)
      evidence_only
      ;;
    action-dry-run)
      run_typed_action 1
      ;;
    action)
      run_typed_action 0
      ;;
    p175-plan)
      make_p175_live_plan
      ;;
    p175-live)
      run_p175_live_harness
      ;;
    teardown-plan)
      teardown_plan
      ;;
    teardown-apply)
      teardown_apply
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
