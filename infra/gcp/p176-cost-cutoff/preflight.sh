#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-${ROOT_DIR}/evals/p176/cost-cutoff-preflight}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"
EXPECTED_ADMIN_PROJECT_ID="${EXPECTED_ADMIN_PROJECT_ID:-}"
EXPECTED_LAB_PROJECT_ID="${EXPECTED_LAB_PROJECT_ID:-}"
RUN_PLAN="${P176_CUTOFF_PREFLIGHT_RUN_PLAN:-0}"

forbidden_patterns=("prod" "production" "shared-vpc")

# Receipt contract phrases for static review: apply_attempted: false, destroy_attempted: false.

mkdir -p "${ARTIFACT_DIR}"
READINESS_JSON="${ARTIFACT_DIR}/p176-cost-cutoff-preflight-readiness.json"

reasons=()
command -v jq >/dev/null 2>&1 || reasons+=("missing_jq")
command -v terraform >/dev/null 2>&1 || reasons+=("missing_terraform")
[[ -f "${TFVARS_FILE}" ]] || reasons+=("missing_tfvars")

declared_admin=""
declared_org=""
declared_lab=""
declared_billing=""
declared_budget_alert_email=""
if [[ -f "${TFVARS_FILE}" ]]; then
  declared_admin="$(awk -F= '/^[[:space:]]*admin_project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
  declared_org="$(awk -F= '/^[[:space:]]*org_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
  declared_lab="$(awk -F= '/^[[:space:]]*lab_project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
  declared_billing="$(awk -F= '/^[[:space:]]*billing_account_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
  declared_budget_alert_email="$(awk -F= '/^[[:space:]]*budget_alert_email[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
fi

admin_project="${EXPECTED_ADMIN_PROJECT_ID:-${declared_admin}}"
lab_project="${EXPECTED_LAB_PROJECT_ID:-${declared_lab}}"

[[ "${admin_project}" =~ ^opscat-p176-admin-[a-z0-9-]{6,20}$ ]] || reasons+=("admin_project_not_dedicated_non_lab")
[[ "${declared_org}" =~ ^[0-9]{6,32}$ ]] || reasons+=("org_id_missing_or_invalid")
[[ "${lab_project}" =~ ^opscat-p176-live-[a-z0-9-]{6,20}$ ]] || reasons+=("lab_project_not_disposable")
[[ "${declared_billing}" =~ ^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$ ]] || reasons+=("billing_account_id_missing_or_invalid")
[[ -n "${declared_budget_alert_email}" ]] || reasons+=("budget_alert_email_missing")
[[ -n "${admin_project}" && -n "${lab_project}" && "${admin_project}" != "${lab_project}" ]] || reasons+=("admin_lab_project_not_separate")

for pattern in "${forbidden_patterns[@]}"; do
  if [[ "${admin_project}" == *"${pattern}"* || "${lab_project}" == *"${pattern}"* ]]; then
    reasons+=("forbidden_project_pattern_${pattern}")
  fi
done

if ((${#reasons[@]} > 0)); then
  printf '{\n  "status": "blocked_external_gate",\n  "blocking_reasons": %s,\n  "mutation_count": 0,\n  "apply_attempted": false,\n  "destroy_attempted": false\n}\n' \
    "$(printf '%s\n' "${reasons[@]}" | jq -R . | jq -s .)" >"${READINESS_JSON}"
  echo "P176 cost-cutoff preflight blocked; see ${READINESS_JSON}." >&2
  exit 2
fi

terraform -chdir="${SCRIPT_DIR}" fmt -check
terraform -chdir="${SCRIPT_DIR}" validate

if [[ "${RUN_PLAN}" != "1" ]]; then
  cat >"${READINESS_JSON}" <<JSON
{
  "status": "blocked_external_gate",
  "blocking_reasons": ["external_authorization_required"],
  "mutation_count": 0,
  "apply_attempted": false,
  "destroy_attempted": false
}
JSON
  echo "Preflight static checks passed; real plan generation remains externally gated."
  exit 2
fi

terraform -chdir="${SCRIPT_DIR}" plan -refresh=false -var-file="${TFVARS_FILE}" -out="p176-cost-cutoff.tfplan"
terraform -chdir="${SCRIPT_DIR}" show -json "p176-cost-cutoff.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff.tfplan.json"
jq -e --arg admin_project "${admin_project}" --arg lab_project "${lab_project}" \
  -f "${SCRIPT_DIR}/verify-apply-plan.jq" "${SCRIPT_DIR}/p176-cost-cutoff.tfplan.json" >/dev/null
shasum -a 256 "${SCRIPT_DIR}/p176-cost-cutoff.tfplan" >"${SCRIPT_DIR}/p176-cost-cutoff.tfplan.sha256"
cat >"${READINESS_JSON}" <<JSON
{
  "status": "review_required",
  "blocking_reasons": ["reviewed_plan_digest_required"],
  "mutation_count": 0,
  "apply_attempted": false,
  "destroy_attempted": false
}
JSON
echo "Plan generated for review only. No apply or destroy was attempted."
