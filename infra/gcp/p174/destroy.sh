#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_PROJECT_ID="${EXPECTED_PROJECT_ID:?set EXPECTED_PROJECT_ID to the frozen P174 project ID}"
EXPECTED_BILLING_ACCOUNT_ID="${EXPECTED_BILLING_ACCOUNT_ID:?set EXPECTED_BILLING_ACCOUNT_ID from local-only runtime configuration}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"

# Command contract: terraform destroy.

forbidden_projects=()
if [[ -n "${P174_FORBIDDEN_PROJECT_IDS:-}" ]]; then
  IFS=', ' read -r -a forbidden_projects <<<"${P174_FORBIDDEN_PROJECT_IDS}"
fi

for forbidden in "${forbidden_projects[@]:-}"; do
  [[ -n "${forbidden}" ]] || continue
  if [[ "${EXPECTED_PROJECT_ID}" == "${forbidden}" ]]; then
    echo "Refusing destroy: forbidden project is not a P174 lab project." >&2
    exit 1
  fi
done

if [[ ! "${EXPECTED_PROJECT_ID}" =~ ^opscat-p174-[a-z0-9-]{6,20}$ ]]; then
  echo "Refusing destroy: EXPECTED_PROJECT_ID must be a dedicated opscat-p174-* project." >&2
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
  awk -F= '/^[[:space:]]*billing_account_id[[:space:]]*=/{gsub(/[ "]/ , "", $2); print $2; exit}' "${TFVARS_FILE}"
)"

if [[ "${declared_project}" != "${EXPECTED_PROJECT_ID}" ]]; then
  echo "Refusing destroy: terraform project_id ${declared_project:-<unset>} does not match EXPECTED_PROJECT_ID ${EXPECTED_PROJECT_ID}." >&2
  exit 1
fi
if [[ "${declared_billing_account}" != "${EXPECTED_BILLING_ACCOUNT_ID}" ]]; then
  echo "Refusing destroy: terraform billing_account_id ${declared_billing_account:-<unset>} does not match EXPECTED_BILLING_ACCOUNT_ID." >&2
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
  terraform -chdir="${SCRIPT_DIR}" plan -destroy -var-file="${TFVARS_FILE}" -out="p174-destroy.tfplan"
  echo "Destroy plan saved to ${SCRIPT_DIR}/p174-destroy.tfplan for project ${EXPECTED_PROJECT_ID}."
  terraform -chdir="${SCRIPT_DIR}" show -json "p174-destroy.tfplan" >"${SCRIPT_DIR}/p174-destroy.tfplan.json"
  shasum -a 256 "${SCRIPT_DIR}/p174-destroy.tfplan" >"${SCRIPT_DIR}/p174-destroy.tfplan.sha256"
else
  : "${EXPECTED_PLAN_SHA256:?set EXPECTED_PLAN_SHA256 to the reviewed destroy-plan digest}"
  [[ -f "${SCRIPT_DIR}/p174-destroy.tfplan" && -f "${SCRIPT_DIR}/p174-destroy.tfplan.sha256" ]] || {
    echo "Refusing destroy apply: saved reviewed plan artifacts are missing." >&2
    exit 1
  }
  actual_plan_sha="$(shasum -a 256 "${SCRIPT_DIR}/p174-destroy.tfplan" | awk '{print $1}')"
  [[ "${actual_plan_sha}" == "${EXPECTED_PLAN_SHA256}" ]] || {
    echo "Refusing destroy apply: reviewed plan digest mismatch." >&2
    exit 1
  }
  terraform -chdir="${SCRIPT_DIR}" show -json "p174-destroy.tfplan" >"${SCRIPT_DIR}/p174-destroy.tfplan.json"
fi

if ! command -v jq >/dev/null; then
  echo "Refusing destroy: jq is required to verify the saved destroy plan before apply." >&2
  exit 1
fi

jq -e --arg project "${EXPECTED_PROJECT_ID}" --arg billing_account "${EXPECTED_BILLING_ACCOUNT_ID}" '
  def has_action($action): (.change.actions | index($action)) != null;

  (.variables.billing_account_id.value == $billing_account)
  and
  ((.resource_changes[]
    | select(.type == "google_project" and .name == "p174")
    | .change.before.number
    | tostring) as $project_number
  | ([.resource_changes[]
    | select(.type == "google_project"
      and .name == "p174"
      and .change.before.project_id == $project
      and .change.after == null
      and .change.actions == ["delete"])] | length) == 1
  and ([.resource_changes[]
    | select(has_action("create") or has_action("update"))] | length) == 0
  and ([.resource_changes[]
    | select(has_action("delete"))] | length) > 0
  and all(.resource_changes[] | select(has_action("delete"));
    (.type as $type
      | (["google_project", "google_billing_project_info", "google_project_service",
          "google_monitoring_notification_channel", "google_billing_budget",
          "google_compute_network", "google_compute_subnetwork", "google_compute_firewall",
          "google_compute_instance", "google_service_account", "google_project_iam_member"]
         | index($type)) != null)
    and (if .type == "google_project" then .change.before.project_id == $project
         elif .type == "google_billing_budget" then
           .address == "google_billing_budget.p174"
           and .change.before.billing_account == $billing_account
           and .change.before.budget_filter[0].projects == [("projects/" + $project_number)]
         else .change.before.project == $project end))
  )
' "${SCRIPT_DIR}/p174-destroy.tfplan.json" >/dev/null

for forbidden in "${forbidden_projects[@]:-}"; do
  [[ -n "${forbidden}" ]] || continue
  if grep -Fq "${forbidden}" "${SCRIPT_DIR}/p174-destroy.tfplan.json"; then
    echo "Refusing destroy: saved plan references a forbidden project." >&2
    exit 1
  fi
done

if [[ "${APPLY_REVIEWED_DESTROY:-0}" != "1" ]]; then
  echo "Destroy plan-only complete. Review it, then rerun with APPLY_REVIEWED_DESTROY=1 and EXPECTED_PLAN_SHA256 using this exact saved plan."
  exit 0
fi

shasum -a 256 -c "${SCRIPT_DIR}/p174-destroy.tfplan.sha256"
# The reviewed destroy plan is applied directly instead of recomputing it with terraform destroy.
terraform -chdir="${SCRIPT_DIR}" apply "p174-destroy.tfplan"
