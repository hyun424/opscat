#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_PROJECT_ID="${EXPECTED_PROJECT_ID:?set EXPECTED_PROJECT_ID to the frozen P174 project ID}"
EXPECTED_BILLING_ACCOUNT_ID="${EXPECTED_BILLING_ACCOUNT_ID:?set EXPECTED_BILLING_ACCOUNT_ID from local-only runtime configuration}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"
EXPIRY_DATE_UTC="20260801"

# Command contract: terraform plan, terraform apply.

forbidden_projects=()
if [[ -n "${P174_FORBIDDEN_PROJECT_IDS:-}" ]]; then
  IFS=', ' read -r -a forbidden_projects <<<"${P174_FORBIDDEN_PROJECT_IDS}"
fi

if [[ ! "${EXPECTED_PROJECT_ID}" =~ ^opscat-p174-[a-z0-9-]{6,20}$ ]]; then
  echo "Refusing deploy: EXPECTED_PROJECT_ID must be a dedicated opscat-p174-* project." >&2
  exit 1
fi

for forbidden in "${forbidden_projects[@]:-}"; do
  [[ -n "${forbidden}" ]] || continue
  if [[ "${EXPECTED_PROJECT_ID}" == "${forbidden}" ]]; then
    echo "Refusing deploy: forbidden project is not a P174 lab project." >&2
    exit 1
  fi
done

today_utc="$(date -u +%Y%m%d)"
if [[ "${today_utc}" > "${EXPIRY_DATE_UTC}" ]]; then
  echo "Refusing deploy: P174 lab expired on ${EXPIRY_DATE_UTC}; destroy remains available for cleanup." >&2
  exit 1
fi

if [[ ! -f "${TFVARS_FILE}" ]]; then
  echo "Missing tfvars file: ${TFVARS_FILE}" >&2
  exit 1
fi

declared_project="$(
  awk -F= '/^[[:space:]]*project_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}"
)"
declared_billing_account="$(
  awk -F= '/^[[:space:]]*billing_account_id[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${TFVARS_FILE}"
)"

if [[ "${declared_project}" != "${EXPECTED_PROJECT_ID}" ]]; then
  echo "Refusing deploy: terraform project_id ${declared_project:-<unset>} does not match EXPECTED_PROJECT_ID ${EXPECTED_PROJECT_ID}." >&2
  exit 1
fi
if [[ "${declared_billing_account}" != "${EXPECTED_BILLING_ACCOUNT_ID}" ]]; then
  echo "Refusing deploy: terraform billing_account_id ${declared_billing_account:-<unset>} does not match EXPECTED_BILLING_ACCOUNT_ID." >&2
  exit 1
fi

verify_saved_plan() {
  command -v jq >/dev/null 2>&1 || {
    echo "Refusing deploy: jq is required to verify the saved plan." >&2
    exit 1
  }
  jq -e --arg project "${EXPECTED_PROJECT_ID}" --arg billing_account "${EXPECTED_BILLING_ACCOUNT_ID}" '
    (.variables.billing_account_id.value == $billing_account)
    and (.variables.project_id.value == $project)
    and ([.resource_changes[]
      | select(.type == "google_project"
        and .name == "p174"
        and .change.actions != ["no-op"])] as $project_changes
      | if ($project_changes | length) == 0 then
          ([.prior_state.values.root_module.resources[]?
            | select(.type == "google_project"
              and .name == "p174"
              and .values.project_id == $project
              and .values.billing_account == $billing_account)] | length) == 1
        else
          (($project_changes | length) == 1
            and ($project_changes[0].change.actions == ["create"]
              or $project_changes[0].change.actions == ["update"])
            and $project_changes[0].change.after.project_id == $project
            and $project_changes[0].change.after.billing_account == $billing_account)
        end)
    and ([.resource_changes[]
      | select((.change.actions | index("update")) != null)] as $updates
      | if ($updates | length) == 0 then true
        else (($updates | length) == 1
          and $updates[0].type == "google_project"
          and $updates[0].name == "p174")
        end)
    and ([.resource_changes[]
      | select((.change.actions | index("delete")) != null)] | length) == 0
    and ([.resource_changes[]
      | select(.change.after.project? != null and .change.after.project != $project)] | length) == 0
    and ([.resource_changes[]
      | select(.type == "google_compute_network" and .change.after.name == "default")] | length) == 0
  ' "${SCRIPT_DIR}/p174.tfplan.json" >/dev/null
  for forbidden in "${forbidden_projects[@]:-}"; do
    [[ -n "${forbidden}" ]] || continue
    if grep -Fq "${forbidden}" "${SCRIPT_DIR}/p174.tfplan.json"; then
      echo "Refusing deploy: saved plan references a forbidden project." >&2
      exit 1
    fi
  done
}

terraform -chdir="${SCRIPT_DIR}" init
terraform -chdir="${SCRIPT_DIR}" fmt -check
terraform -chdir="${SCRIPT_DIR}" validate

if [[ "${APPLY_REVIEWED_PLAN:-0}" != "1" ]]; then
  terraform -chdir="${SCRIPT_DIR}" plan -var-file="${TFVARS_FILE}" -out="p174.tfplan"
  echo "Plan saved to ${SCRIPT_DIR}/p174.tfplan for project ${EXPECTED_PROJECT_ID}."
  terraform -chdir="${SCRIPT_DIR}" show -json "p174.tfplan" >"${SCRIPT_DIR}/p174.tfplan.json"
  verify_saved_plan
  shasum -a 256 "${SCRIPT_DIR}/p174.tfplan" >"${SCRIPT_DIR}/p174.tfplan.sha256"
  echo "Plan-only complete. Review p174.tfplan.json, then rerun with APPLY_REVIEWED_PLAN=1 and EXPECTED_PLAN_SHA256 using this exact saved plan."
  exit 0
fi

: "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed p174.tfplan digest}"
[[ -f "${SCRIPT_DIR}/p174.tfplan" && -f "${SCRIPT_DIR}/p174.tfplan.sha256" ]] || {
  echo "Refusing apply: saved reviewed plan artifacts are missing." >&2
  exit 1
}
actual_plan_sha="$(shasum -a 256 "${SCRIPT_DIR}/p174.tfplan" | awk '{print $1}')"
if [[ "${actual_plan_sha}" != "${EXPECTED_PLAN_SHA256}" ]]; then
  echo "Refusing apply: reviewed plan digest mismatch." >&2
  exit 1
fi
shasum -a 256 -c "${SCRIPT_DIR}/p174.tfplan.sha256"
terraform -chdir="${SCRIPT_DIR}" show -json "p174.tfplan" >"${SCRIPT_DIR}/p174.tfplan.json"
verify_saved_plan
terraform -chdir="${SCRIPT_DIR}" apply "p174.tfplan"
