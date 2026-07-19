#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_PROJECT_ID="${EXPECTED_PROJECT_ID:?set EXPECTED_PROJECT_ID to the frozen P176 live project ID}"
EXPECTED_BILLING_ACCOUNT_ID="${EXPECTED_BILLING_ACCOUNT_ID:?set EXPECTED_BILLING_ACCOUNT_ID from local uncommitted configuration}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"

# Command contract: terraform destroy.

forbidden_projects=(
  "prod"
  "production"
  "shared-vpc"
)

if [[ ! "${EXPECTED_PROJECT_ID}" =~ ^opscat-p176-live-[a-z0-9-]{6,20}$ ]]; then
  echo "Refusing destroy: EXPECTED_PROJECT_ID must be a dedicated opscat-p176-live-* project." >&2
  exit 1
fi

for forbidden in "${forbidden_projects[@]}"; do
  if [[ "${EXPECTED_PROJECT_ID}" == *"${forbidden}"* ]]; then
    echo "Refusing destroy: forbidden project pattern ${forbidden} is not allowed for a P176 live lab project." >&2
    exit 1
  fi
done

if [[ ! -f "${TFVARS_FILE}" ]]; then
  echo "Missing tfvars file: ${TFVARS_FILE}" >&2
  exit 1
fi

declared_project="$(
  awk -F= '/^[[:space:]]*project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}"
)"
declared_billing_account="$(
  awk -F= '/^[[:space:]]*billing_account_id[[:space:]]*=/{gsub(/[ "]/ , "", $2); print $2; exit}' "${TFVARS_FILE}"
)"

if [[ "${declared_project}" != "${EXPECTED_PROJECT_ID}" ]]; then
  echo "Refusing destroy: terraform project_id ${declared_project:-<unset>} does not match EXPECTED_PROJECT_ID ${EXPECTED_PROJECT_ID}." >&2
  exit 1
fi
if [[ -z "${declared_billing_account}" || "${declared_billing_account}" != "${EXPECTED_BILLING_ACCOUNT_ID}" ]]; then
  echo "Refusing destroy: terraform billing_account_id is missing or does not match EXPECTED_BILLING_ACCOUNT_ID." >&2
  exit 1
fi

state_project="$(terraform -chdir="${SCRIPT_DIR}" output -raw project_id 2>/dev/null || true)"
if [[ -n "${state_project}" && "${state_project}" != "${EXPECTED_PROJECT_ID}" ]]; then
  echo "Refusing destroy: Terraform state project ${state_project} does not match EXPECTED_PROJECT_ID ${EXPECTED_PROJECT_ID}." >&2
  exit 1
fi

terraform -chdir="${SCRIPT_DIR}" fmt -check
terraform -chdir="${SCRIPT_DIR}" validate

if [[ "${APPLY_REVIEWED_DESTROY:-0}" != "1" ]]; then
  terraform -chdir="${SCRIPT_DIR}" plan -destroy -refresh=false -var-file="${TFVARS_FILE}" -out="p176-live-destroy.tfplan"
  echo "Destroy plan saved to ${SCRIPT_DIR}/p176-live-destroy.tfplan for project ${EXPECTED_PROJECT_ID}."
  terraform -chdir="${SCRIPT_DIR}" show -json "p176-live-destroy.tfplan" >"${SCRIPT_DIR}/p176-live-destroy.tfplan.json"
  shasum -a 256 "${SCRIPT_DIR}/p176-live-destroy.tfplan" >"${SCRIPT_DIR}/p176-live-destroy.tfplan.sha256"
else
  : "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed destroy-plan digest}"
  [[ -f "${SCRIPT_DIR}/p176-live-destroy.tfplan" && -f "${SCRIPT_DIR}/p176-live-destroy.tfplan.sha256" ]] || {
    echo "Refusing destroy apply: saved reviewed plan artifacts are missing." >&2
    exit 1
  }
  actual_plan_sha="$(shasum -a 256 "${SCRIPT_DIR}/p176-live-destroy.tfplan" | awk '{print $1}')"
  [[ "${actual_plan_sha}" == "${EXPECTED_PLAN_SHA256}" ]] || {
    echo "Refusing destroy apply: reviewed plan digest mismatch." >&2
    exit 1
  }
  terraform -chdir="${SCRIPT_DIR}" show -json "p176-live-destroy.tfplan" >"${SCRIPT_DIR}/p176-live-destroy.tfplan.json"
fi

verify_destroy_plan() {
  command -v jq >/dev/null 2>&1 || {
    echo "Refusing destroy: jq is required to verify the saved destroy plan before apply." >&2
    exit 1
  }
  jq -e --arg project "${EXPECTED_PROJECT_ID}" \
    --arg billing_account "${EXPECTED_BILLING_ACCOUNT_ID}" \
    -f "${SCRIPT_DIR}/verify-destroy-plan.jq" \
    "${SCRIPT_DIR}/p176-live-destroy.tfplan.json" >/dev/null

  for forbidden in "${forbidden_projects[@]}"; do
    if grep -Fq "${forbidden}" "${SCRIPT_DIR}/p176-live-destroy.tfplan.json"; then
      echo "Refusing destroy: saved plan references forbidden project pattern ${forbidden}." >&2
      exit 1
    fi
  done
}

verify_destroy_plan

if [[ "${APPLY_REVIEWED_DESTROY:-0}" != "1" ]]; then
  echo "Destroy plan-only complete. Review it, then rerun with APPLY_REVIEWED_DESTROY=1 and EXPECTED_PLAN_SHA256 using this exact saved plan."
  exit 0
fi

shasum -a 256 -c "${SCRIPT_DIR}/p176-live-destroy.tfplan.sha256"
terraform -chdir="${SCRIPT_DIR}" apply "p176-live-destroy.tfplan"
