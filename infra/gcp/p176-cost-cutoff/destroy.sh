#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_ADMIN_PROJECT_ID="${EXPECTED_ADMIN_PROJECT_ID:?set EXPECTED_ADMIN_PROJECT_ID to the P176 admin project ID}"
EXPECTED_LAB_PROJECT_ID="${EXPECTED_LAB_PROJECT_ID:?set EXPECTED_LAB_PROJECT_ID to the P176 disposable lab project ID}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"

# Command contract: terraform destroy.

forbidden_patterns=("prod" "production" "shared-vpc")

for pattern in "${forbidden_patterns[@]}"; do
  if [[ "${EXPECTED_ADMIN_PROJECT_ID}" == *"${pattern}"* || "${EXPECTED_LAB_PROJECT_ID}" == *"${pattern}"* ]]; then
    echo "Refusing destroy: expected project matches forbidden pattern ${pattern}." >&2
    exit 1
  fi
done

[[ "${EXPECTED_ADMIN_PROJECT_ID}" =~ ^opscat-p176-admin-[a-z0-9-]{6,20}$ ]] || {
  echo "Refusing destroy: EXPECTED_ADMIN_PROJECT_ID must be opscat-p176-admin-*." >&2
  exit 1
}
[[ "${EXPECTED_LAB_PROJECT_ID}" =~ ^opscat-p176-live-[a-z0-9-]{6,20}$ ]] || {
  echo "Refusing destroy: EXPECTED_LAB_PROJECT_ID must be opscat-p176-live-*." >&2
  exit 1
}
[[ -f "${TFVARS_FILE}" ]] || {
  echo "Missing tfvars file: ${TFVARS_FILE}" >&2
  exit 1
}
declared_admin="$(awk -F= '/^[[:space:]]*admin_project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
declared_lab="$(awk -F= '/^[[:space:]]*lab_project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
declared_org="$(awk -F= '/^[[:space:]]*org_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
declared_billing="$(awk -F= '/^[[:space:]]*billing_account_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
if [[ "${declared_admin}" != "${EXPECTED_ADMIN_PROJECT_ID}" || "${declared_lab}" != "${EXPECTED_LAB_PROJECT_ID}" ]]; then
  echo "Refusing destroy: tfvars projects must match EXPECTED_ADMIN_PROJECT_ID and EXPECTED_LAB_PROJECT_ID." >&2
  exit 1
fi
if [[ ! "${declared_org}" =~ ^[0-9]{6,32}$ || ! "${declared_billing}" =~ ^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$ ]]; then
  echo "Refusing destroy: tfvars must supply local org_id and billing_account_id for plan verification." >&2
  exit 1
fi

verify_destroy_plan() {
  command -v jq >/dev/null 2>&1 || {
    echo "Refusing destroy: jq is required to verify the saved destroy plan." >&2
    exit 1
  }
  jq -e --arg admin_project "${EXPECTED_ADMIN_PROJECT_ID}" \
    --arg lab_project "${EXPECTED_LAB_PROJECT_ID}" \
    -f "${SCRIPT_DIR}/verify-destroy-plan.jq" \
    "${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan.json" >/dev/null
}

terraform -chdir="${SCRIPT_DIR}" fmt -check
terraform -chdir="${SCRIPT_DIR}" validate

if [[ "${APPLY_REVIEWED_DESTROY:-0}" != "1" ]]; then
  terraform -chdir="${SCRIPT_DIR}" plan -destroy -refresh=false -var-file="${TFVARS_FILE}" -out="p176-cost-cutoff-destroy.tfplan"
  terraform -chdir="${SCRIPT_DIR}" show -json "p176-cost-cutoff-destroy.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan.json"
  verify_destroy_plan
  shasum -a 256 "${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan.sha256"
  echo "Destroy plan-only complete. Review p176-cost-cutoff-destroy.tfplan.json, then rerun with APPLY_REVIEWED_DESTROY=1 and EXPECTED_PLAN_SHA256."
  exit 0
fi

: "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed destroy-plan digest}"
[[ -f "${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan" && -f "${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan.sha256" ]] || {
  echo "Refusing destroy apply: saved reviewed plan artifacts are missing." >&2
  exit 1
}
actual_plan_sha="$(shasum -a 256 "${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan" | awk '{print $1}')"
[[ "${actual_plan_sha}" == "${EXPECTED_PLAN_SHA256}" ]] || {
  echo "Refusing destroy apply: reviewed plan digest mismatch." >&2
  exit 1
}
terraform -chdir="${SCRIPT_DIR}" show -json "p176-cost-cutoff-destroy.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan.json"
verify_destroy_plan
shasum -a 256 -c "${SCRIPT_DIR}/p176-cost-cutoff-destroy.tfplan.sha256"
terraform -chdir="${SCRIPT_DIR}" apply "p176-cost-cutoff-destroy.tfplan"
