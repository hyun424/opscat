#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_ADMIN_PROJECT_ID="${EXPECTED_ADMIN_PROJECT_ID:?set EXPECTED_ADMIN_PROJECT_ID to the P176 admin project ID}"
EXPECTED_LAB_PROJECT_ID="${EXPECTED_LAB_PROJECT_ID:?set EXPECTED_LAB_PROJECT_ID to the P176 disposable lab project ID}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"

# Command contract: terraform plan, terraform apply.

forbidden_patterns=("prod" "production" "shared-vpc")

reject_project() {
  local label="$1"
  local project="$2"
  local regex="$3"
  if [[ ! "${project}" =~ ${regex} ]]; then
    echo "Refusing deploy: ${label} has an invalid dedicated P176 project pattern." >&2
    exit 1
  fi
  local pattern
  for pattern in "${forbidden_patterns[@]}"; do
    if [[ "${project}" == *"${pattern}"* ]]; then
      echo "Refusing deploy: ${label} matches forbidden pattern ${pattern}." >&2
      exit 1
    fi
  done
}

reject_project "EXPECTED_ADMIN_PROJECT_ID" "${EXPECTED_ADMIN_PROJECT_ID}" '^opscat-p176-admin-[a-z0-9-]{6,20}$'
reject_project "EXPECTED_LAB_PROJECT_ID" "${EXPECTED_LAB_PROJECT_ID}" '^opscat-p176-live-[a-z0-9-]{6,20}$'
if [[ "${EXPECTED_ADMIN_PROJECT_ID}" == "${EXPECTED_LAB_PROJECT_ID}" ]]; then
  echo "Refusing deploy: admin and lab projects must be separate." >&2
  exit 1
fi

[[ -f "${TFVARS_FILE}" ]] || {
  echo "Missing tfvars file: ${TFVARS_FILE}" >&2
  exit 1
}

declared_admin="$(awk -F= '/^[[:space:]]*admin_project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
declared_org="$(awk -F= '/^[[:space:]]*org_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
declared_lab="$(awk -F= '/^[[:space:]]*lab_project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
declared_billing="$(awk -F= '/^[[:space:]]*billing_account_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
if [[ "${declared_admin}" != "${EXPECTED_ADMIN_PROJECT_ID}" || "${declared_lab}" != "${EXPECTED_LAB_PROJECT_ID}" ]]; then
  echo "Refusing deploy: tfvars projects must match EXPECTED_ADMIN_PROJECT_ID and EXPECTED_LAB_PROJECT_ID." >&2
  exit 1
fi
if [[ ! "${declared_org}" =~ ^[0-9]{6,32}$ || ! "${declared_billing}" =~ ^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$ ]]; then
  echo "Refusing deploy: tfvars must supply local org_id and billing_account_id." >&2
  exit 1
fi

verify_saved_plan() {
  command -v jq >/dev/null 2>&1 || {
    echo "Refusing deploy: jq is required to verify the saved plan." >&2
    exit 1
  }
  jq -e --arg admin_project "${EXPECTED_ADMIN_PROJECT_ID}" \
    --arg lab_project "${EXPECTED_LAB_PROJECT_ID}" \
    -f "${SCRIPT_DIR}/verify-apply-plan.jq" \
    "${SCRIPT_DIR}/p176-cost-cutoff.tfplan.json" >/dev/null
}

terraform -chdir="${SCRIPT_DIR}" init
terraform -chdir="${SCRIPT_DIR}" fmt -check
terraform -chdir="${SCRIPT_DIR}" validate

if [[ "${APPLY_REVIEWED_PLAN:-0}" != "1" ]]; then
  terraform -chdir="${SCRIPT_DIR}" plan -refresh=false -var-file="${TFVARS_FILE}" -out="p176-cost-cutoff.tfplan"
  terraform -chdir="${SCRIPT_DIR}" show -json "p176-cost-cutoff.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff.tfplan.json"
  verify_saved_plan
  shasum -a 256 "${SCRIPT_DIR}/p176-cost-cutoff.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff.tfplan.sha256"
  echo "Plan-only complete. Review p176-cost-cutoff.tfplan.json, then rerun with APPLY_REVIEWED_PLAN=1 and EXPECTED_PLAN_SHA256."
  exit 0
fi

: "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed p176-cost-cutoff.tfplan digest}"
[[ -f "${SCRIPT_DIR}/p176-cost-cutoff.tfplan" && -f "${SCRIPT_DIR}/p176-cost-cutoff.tfplan.sha256" ]] || {
  echo "Refusing apply: saved reviewed plan artifacts are missing." >&2
  exit 1
}
actual_plan_sha="$(shasum -a 256 "${SCRIPT_DIR}/p176-cost-cutoff.tfplan" | awk '{print $1}')"
[[ "${actual_plan_sha}" == "${EXPECTED_PLAN_SHA256}" ]] || {
  echo "Refusing apply: reviewed plan digest mismatch." >&2
  exit 1
}
shasum -a 256 -c "${SCRIPT_DIR}/p176-cost-cutoff.tfplan.sha256"
terraform -chdir="${SCRIPT_DIR}" show -json "p176-cost-cutoff.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff.tfplan.json"
verify_saved_plan

APPLY_ATTEMPT_DIR="${SCRIPT_DIR}/.terraform/p176-cost-cutoff-apply-attempts"
APPLY_ATTEMPT_RECEIPT="${APPLY_ATTEMPT_DIR}/${actual_plan_sha}.json"
APPLY_ATTEMPT_INDEX="${SCRIPT_DIR}/.terraform/p176-cost-cutoff-apply-attempt.json"
mkdir -p "${APPLY_ATTEMPT_DIR}"

if [[ -f "${APPLY_ATTEMPT_RECEIPT}" ]]; then
  attempted_plan_sha256="$(jq -r '.plan_sha256 // empty' "${APPLY_ATTEMPT_RECEIPT}")"
  if [[ "${attempted_plan_sha256}" == "${actual_plan_sha}" ]]; then
    echo "Refusing apply: this reviewed plan digest already has an apply attempt receipt." >&2
    echo "Generate and independently review a fresh plan against the current Terraform state." >&2
    exit 1
  fi
  echo "Refusing apply: malformed apply attempt receipt for this plan digest." >&2
  exit 1
fi

set -o noclobber
if ! : >"${APPLY_ATTEMPT_RECEIPT}"; then
  set +o noclobber
  echo "Refusing apply: this reviewed plan digest already has an apply attempt receipt." >&2
  exit 1
fi
set +o noclobber
chmod 600 "${APPLY_ATTEMPT_RECEIPT}"

apply_started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

write_apply_attempt_receipt() {
  local status="$1"
  local exit_code="$2"
  local finished_at="$3"
  local receipt_tmp
  local index_tmp
  receipt_tmp="$(mktemp "${APPLY_ATTEMPT_DIR}/.attempt.XXXXXX")"
  index_tmp="$(mktemp "${SCRIPT_DIR}/.terraform/.attempt-index.XXXXXX")"
  jq -n \
    --arg plan_sha256 "${actual_plan_sha}" \
    --arg apply_started_at "${apply_started_at}" \
    --arg apply_finished_at "${finished_at}" \
    --arg status "${status}" \
    --argjson exit_code "${exit_code}" \
    '{
      plan_sha256: $plan_sha256,
      apply_started_at: $apply_started_at,
      apply_finished_at: (if $apply_finished_at == "" then null else $apply_finished_at end),
      status: $status,
      exit_code: $exit_code,
      contains_cloud_identifiers: false
    }' >"${receipt_tmp}"
  cp "${receipt_tmp}" "${index_tmp}"
  mv "${receipt_tmp}" "${APPLY_ATTEMPT_RECEIPT}"
  mv "${index_tmp}" "${APPLY_ATTEMPT_INDEX}"
}

write_apply_attempt_receipt "started" 0 ""
if terraform -chdir="${SCRIPT_DIR}" apply "p176-cost-cutoff.tfplan"; then
  write_apply_attempt_receipt "succeeded" 0 "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
else
  apply_exit_code=$?
  write_apply_attempt_receipt "failed" "${apply_exit_code}" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  exit "${apply_exit_code}"
fi
