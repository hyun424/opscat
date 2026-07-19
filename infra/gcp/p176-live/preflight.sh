#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-${ROOT_DIR}/evals/p176/live-preflight}"
TFVARS_FILE="${TFVARS_FILE:-${SCRIPT_DIR}/terraform.tfvars}"
EXPECTED_PROJECT_ID="${EXPECTED_PROJECT_ID:-}"
EXPECTED_BILLING_ACCOUNT_ID="${EXPECTED_BILLING_ACCOUNT_ID:-}"
RUN_PLAN="${P176_PREFLIGHT_RUN_PLAN:-0}"
PLAN_GENERATED_THIS_RUN=false
GCLOUD_STRUCTURED_SECRET_CONTENT_PATTERN='-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"(type)"[[:space:]]*:[[:space:]]*"service_account"|"(private_key|private_key_id|refresh_token|access_token|id_token|client_secret)"[[:space:]]*:|ya29\.[A-Za-z0-9._-]{10,}|AIza[0-9A-Za-z_-]{20,}'
GCLOUD_TEXT_SECRET_CONTENT_PATTERN='-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|ya29\.[A-Za-z0-9._-]{10,}|AIza[0-9A-Za-z_-]{20,}'
PUBLIC_EVIDENCE_SENSITIVE_CONTENT_PATTERN='-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"(private_key|private_key_id|client_email|client_id|refresh_token|access_token|id_token|client_secret|token_uri)"[[:space:]]*:|ya29\.|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|billingAccounts/[0-9A-Fa-f-]{6}-[0-9A-Fa-f-]{6}-[0-9A-Fa-f-]{6}|organizations/[0-9]{6,}|opscat-p176-(live|admin)-[a-z0-9-]{6,20}|/Users/|/private/|/var/folders/|/tmp/|[A-Za-z]:\\'

READINESS_JSON="${ARTIFACT_DIR}/p176-live-preflight-readiness.json"
BOUNDARY_JSON="${ARTIFACT_DIR}/p176-live-preflight-boundary.json"
RECEIPTS_JSON="${ARTIFACT_DIR}/p176-live-preflight-receipts.json"
PLAN_PROCEDURE_MD="${ARTIFACT_DIR}/p176-live-plan-generation-procedure.md"

if [[ -L "${ARTIFACT_DIR}" ]]; then
  echo "Refusing symlink artifact directory." >&2
  exit 70
fi
mkdir -p "${ARTIFACT_DIR}"
if [[ ! -d "${ARTIFACT_DIR}" || -L "${ARTIFACT_DIR}" ]]; then
  echo "Refusing unsafe artifact directory." >&2
  exit 70
fi

TMP_DIR="$(mktemp -d "${ARTIFACT_DIR}/.tmp.p176-preflight.XXXXXX")"
chmod 700 "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT

forbidden_projects=(
  "prod"
  "production"
  "shared-vpc"
)

artifact_targets=(
  "${READINESS_JSON}"
  "${BOUNDARY_JSON}"
  "${RECEIPTS_JSON}"
  "${PLAN_PROCEDURE_MD}"
)

stale_raw_artifacts=(
  "terraform-version.stdout.txt"
  "terraform-version.stderr.txt"
  "terraform-fmt.stdout.txt"
  "terraform-fmt.stderr.txt"
  "terraform-validate.stdout.txt"
  "terraform-validate.stderr.txt"
  "gcloud-version.stdout.txt"
  "gcloud-version.stderr.txt"
  "gcloud-config.stdout.json"
  "gcloud-config.stderr.txt"
  "gcloud-auth-active.stdout.json"
  "gcloud-auth-active.stderr.txt"
  "gcloud-billing-accounts.stdout.json"
  "gcloud-billing-accounts.stderr.txt"
  "gcloud-key-filename-scan.txt"
  "gcloud-credential-content-scan.txt"
  "artifact-sensitive-content-scan.txt"
  "gcloud-key-filename-scan.stderr.txt"
)

assert_no_symlink_target() {
  local path="$1"
  if [[ -L "${path}" ]]; then
    echo "Refusing symlink artifact output target." >&2
    exit 70
  fi
}

assert_artifact_targets_safe() {
  local path
  for path in "${artifact_targets[@]}"; do
    assert_no_symlink_target "${path}"
  done
}

remove_stale_raw_artifacts() {
  local name path
  for name in "${stale_raw_artifacts[@]}"; do
    path="${ARTIFACT_DIR}/${name}"
    if [[ -e "${path}" || -L "${path}" ]]; then
      rm -f -- "${path}"
    fi
  done
}

private_temp_file() {
  local name="$1"
  mktemp "${TMP_DIR}/${name}.XXXXXX"
}

install_artifact() {
  local src="$1"
  local dest="$2"
  assert_no_symlink_target "${dest}"
  chmod 600 "${src}"
  mv -f -- "${src}" "${dest}"
}

assert_artifact_targets_safe
remove_stale_raw_artifacts

json_string_array() {
  if (($# == 0)); then
    jq -n '[]'
  else
    printf '%s\n' "$@" | jq -R . | jq -s .
  fi
}

sha256_value() {
  if [[ -f "$1" ]]; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    printf ''
  fi
}

byte_count() {
  if [[ -f "$1" ]]; then
    wc -c <"$1" | tr -d '[:space:]'
  else
    printf '0'
  fi
}

stat_uid() {
  stat -f '%u' "$1" 2>/dev/null || stat -c '%u' "$1"
}

stat_mode() {
  stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1"
}

logical_path() {
  local path="$1"
  if [[ "${path}" == "${ROOT_DIR}/"* ]]; then
    printf '%s' "${path#${ROOT_DIR}/}"
  else
    basename "${path}"
  fi
}

capture_command() {
  local name="$1"
  shift
  local stdout_path="${TMP_DIR}/${name}.stdout"
  local stderr_path="${TMP_DIR}/${name}.stderr"
  if "$@" >"${stdout_path}" 2>"${stderr_path}"; then
    jq -n \
      --arg status "pass" \
      --arg stdout_sha "$(sha256_value "${stdout_path}")" \
      --arg stderr_sha "$(sha256_value "${stderr_path}")" \
      --argjson stdout_bytes "$(byte_count "${stdout_path}")" \
      --argjson stderr_bytes "$(byte_count "${stderr_path}")" \
      '{status:$status, stdout_sha256:$stdout_sha, stderr_sha256:$stderr_sha, stdout_bytes:$stdout_bytes, stderr_bytes:$stderr_bytes}'
  else
    local rc=$?
    jq -n \
      --arg status "fail" \
      --arg stdout_sha "$(sha256_value "${stdout_path}")" \
      --arg stderr_sha "$(sha256_value "${stderr_path}")" \
      --argjson stdout_bytes "$(byte_count "${stdout_path}")" \
      --argjson stderr_bytes "$(byte_count "${stderr_path}")" \
      --argjson rc "${rc}" \
      '{status:$status, exit_code:$rc, stdout_sha256:$stdout_sha, stderr_sha256:$stderr_sha, stdout_bytes:$stdout_bytes, stderr_bytes:$stderr_bytes}'
  fi
}

redacted_receipt() {
  local receipt="$1"
  jq '{status, exit_code, stdout_sha256, stderr_sha256, stdout_bytes, stderr_bytes}' <<<"${receipt}"
}

read_tfvar() {
  local key="$1"
  [[ -f "${TFVARS_FILE}" ]] || return 0
  awk -F= -v key="${key}" '
    $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)
      gsub(/^"|"$/, "", $2)
      print $2
      exit
    }
  ' "${TFVARS_FILE}"
}

write_plan_procedure() {
  local tmp
  tmp="$(private_temp_file "plan-procedure.md")"
  cat >"${tmp}" <<'MARKDOWN'
# P176 Reviewed Terraform Plan Procedure

This procedure is plan-only until a human review binds the exact digest.

1. Copy `infra/gcp/p176-live/terraform.tfvars.template` to `terraform.tfvars`.
2. Replace every placeholder with nonsecret values:
   - `billing_account_id`: GCP billing account ID from local billing records.
   - `project_id`: existing `opscat-p176-live-*` lab project ID from `../p176-cost-cutoff`.
   - `cost_cutoff_budget_topic_name`: admin topic exported by `../p176-cost-cutoff`.
   - `ssh_admin_members`: IAP/OS Login administrators only.
   - keep `opscat_principal = ""` unless recording an evidence-only principal.
3. Export `EXPECTED_PROJECT_ID` and `EXPECTED_BILLING_ACCOUNT_ID`; these must match local `terraform.tfvars`.
4. Confirm the active `gcloud` identity can see the expected billing account from local, uncommitted configuration.
5. Generate the reviewed plan only:

```bash
EXPECTED_PROJECT_ID=<fresh opscat-p176-live-* project> \
EXPECTED_BILLING_ACCOUNT_ID=<billing account id from local tfvars> \
P176_PREFLIGHT_RUN_PLAN=1 \
infra/gcp/p176-live/preflight.sh
```

6. Review `p176-live.tfplan.json` with `verify-apply-plan.jq` and the generated preflight receipts.
7. Apply remains blocked until a human supplies the exact reviewed digest:

```bash
APPLY_REVIEWED_PLAN=1 \
EXPECTED_PROJECT_ID=<fresh opscat-p176-live-* project> \
EXPECTED_BILLING_ACCOUNT_ID=<billing account id from local tfvars> \
EXPECTED_PLAN_SHA256=<reviewed p176-live.tfplan sha256> \
infra/gcp/p176-live/deploy.sh
```

Do not run `terraform apply`, `terraform destroy`, API enablement, or project creation during preflight.
MARKDOWN
  install_artifact "${tmp}" "${PLAN_PROCEDURE_MD}"
}

write_plan_procedure

declared_project="$(read_tfvar project_id)"
expected_project="${EXPECTED_PROJECT_ID:-${declared_project}}"
declared_billing="$(read_tfvar billing_account_id)"

reasons=()
warnings=()

command -v jq >/dev/null 2>&1 || reasons+=("missing_jq")
command -v shasum >/dev/null 2>&1 || reasons+=("missing_shasum")
command -v terraform >/dev/null 2>&1 || reasons+=("missing_terraform")
command -v gcloud >/dev/null 2>&1 || reasons+=("missing_gcloud")

[[ -f "${SCRIPT_DIR}/terraform.tfvars.template" ]] || reasons+=("missing_tfvars_template")
[[ -f "${TFVARS_FILE}" ]] || reasons+=("missing_tfvars")

if [[ -z "${expected_project}" ]]; then
  reasons+=("missing_expected_project_id")
elif [[ ! "${expected_project}" =~ ^opscat-p176-live-[a-z0-9-]{6,20}$ ]]; then
  reasons+=("expected_project_id_not_p176_dedicated")
fi
if [[ -z "${EXPECTED_BILLING_ACCOUNT_ID}" ]]; then
  reasons+=("missing_expected_billing_account_id")
elif [[ ! "${EXPECTED_BILLING_ACCOUNT_ID}" =~ ^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$ ]]; then
  reasons+=("expected_billing_account_id_invalid")
fi

for forbidden in "${forbidden_projects[@]}"; do
    if [[ "${expected_project}" == *"${forbidden}"* ]]; then
    reasons+=("expected_project_id_forbidden")
  fi
done

if [[ -n "${EXPECTED_PROJECT_ID}" && -n "${declared_project}" && "${EXPECTED_PROJECT_ID}" != "${declared_project}" ]]; then
  reasons+=("expected_project_id_mismatch_tfvars")
fi

if [[ -z "${declared_billing}" ]]; then
  reasons+=("missing_tfvars_billing_account_id")
elif [[ -n "${EXPECTED_BILLING_ACCOUNT_ID}" && "${declared_billing}" != "${EXPECTED_BILLING_ACCOUNT_ID}" ]]; then
  reasons+=("expected_billing_account_id_mismatch_tfvars")
fi

terraform_version="$(capture_command terraform-version terraform -chdir="${SCRIPT_DIR}" version)"
terraform_fmt="$(capture_command terraform-fmt terraform -chdir="${SCRIPT_DIR}" fmt -check)"
terraform_validate="$(capture_command terraform-validate terraform -chdir="${SCRIPT_DIR}" validate)"
gcloud_version="$(capture_command gcloud-version gcloud --version)"
gcloud_config="$(capture_command gcloud-config gcloud config list --format=json)"
gcloud_auth="$(capture_command gcloud-auth-active gcloud auth list --filter=status:ACTIVE --format=json)"
gcloud_billing="$(capture_command gcloud-billing-accounts gcloud billing accounts list --format=json)"

active_project=""
billing_visible="false"

if [[ "$(jq -r '.status' <<<"${gcloud_config}")" == "pass" ]]; then
  active_project="$(jq -r '.core.project // ""' "${TMP_DIR}/gcloud-config.stdout")"
else
  reasons+=("gcloud_config_unreadable")
fi

if [[ "$(jq -r '.status' <<<"${gcloud_auth}")" == "pass" ]]; then
  auth_count="$(jq '[.[] | select(.status == "ACTIVE")] | length' "${TMP_DIR}/gcloud-auth-active.stdout")"
  [[ "${auth_count}" == "1" ]] || reasons+=("gcloud_active_identity_missing_or_ambiguous")
else
  reasons+=("gcloud_auth_unreadable")
fi

if [[ -n "${active_project}" ]]; then
  for forbidden in "${forbidden_projects[@]}"; do
    if [[ "${active_project}" == *"${forbidden}"* ]]; then
      reasons+=("gcloud_active_project_forbidden")
    fi
  done
fi

if [[ "$(jq -r '.status' <<<"${gcloud_billing}")" == "pass" ]]; then
  if [[ -n "${EXPECTED_BILLING_ACCOUNT_ID}" ]]; then
    billing_visible="$(jq --arg billing "billingAccounts/${EXPECTED_BILLING_ACCOUNT_ID}" 'any(.[]; .name == $billing and .open == true)' "${TMP_DIR}/gcloud-billing-accounts.stdout")"
    [[ "${billing_visible}" == "true" ]] || reasons+=("expected_billing_account_not_visible_open")
  fi
else
  reasons+=("gcloud_billing_accounts_unreadable")
fi

if [[ "$(jq -r '.status' <<<"${terraform_fmt}")" != "pass" ]]; then
  reasons+=("terraform_fmt_check_failed")
fi
if [[ "$(jq -r '.status' <<<"${terraform_validate}")" != "pass" ]]; then
  reasons+=("terraform_validate_failed")
fi

if [[ -d "${HOME}/.config/gcloud" ]]; then
  gcloud_config_dir="${HOME}/.config/gcloud"
  current_uid="$(id -u)"

  is_known_gcloud_store() {
    local path="$1"
    is_strict_gcloud_credential_store "${path}" || is_gcloud_metadata_file "${path}"
  }

  is_strict_gcloud_credential_store() {
    local path="$1"
    case "${path}" in
      "${gcloud_config_dir}"/*/credentials.db | "${gcloud_config_dir}/credentials.db" | \
      "${gcloud_config_dir}"/*/access_tokens.db | "${gcloud_config_dir}/access_tokens.db" | \
      "${gcloud_config_dir}"/*/application_default_credentials.json | "${gcloud_config_dir}/application_default_credentials.json" | \
      "${gcloud_config_dir}"/*/adc.json | "${gcloud_config_dir}/adc.json")
        return 0
        ;;
      *)
        return 1
        ;;
    esac
  }

  is_gcloud_metadata_file() {
    local path="$1"
    case "${path}" in
      "${gcloud_config_dir}/active_config" | \
      "${gcloud_config_dir}/.last_update_check" | \
      "${gcloud_config_dir}/.last_update_check.json" | \
      "${gcloud_config_dir}/configurations"/config_*)
        return 0
        ;;
      *)
        return 1
        ;;
    esac
  }

  is_trusted_gcloud_installed_code_or_cache() {
    local path="$1"
    case "${path}" in
      "${gcloud_config_dir}/platform/"*"/site-packages/"* | \
      "${gcloud_config_dir}/platform/"*"/__pycache__/"* | \
      "${gcloud_config_dir}/virtenv/"*"/site-packages/"* | \
      "${gcloud_config_dir}/virtenv/"*"/__pycache__/"*)
        return 0
        ;;
      *)
        return 1
        ;;
    esac
  }

  validate_regular_current_user_file() {
    local path="$1"
    local reason_prefix="$2"
    local owner
    if [[ -L "${path}" ]]; then
      reasons+=("unsafe_gcloud_${reason_prefix}_symlink")
      return 0
    fi
    if [[ ! -f "${path}" ]]; then
      reasons+=("unsafe_gcloud_${reason_prefix}_not_regular_file")
      return 0
    fi
    owner="$(stat_uid "${path}")"
    if [[ "${owner}" != "${current_uid}" ]]; then
      reasons+=("unsafe_gcloud_${reason_prefix}_owner")
    fi
  }

  validate_strict_gcloud_credential_store() {
    local path="$1"
    local mode
    validate_regular_current_user_file "${path}" "credential_store"
    [[ -f "${path}" && ! -L "${path}" ]] || return 0
    mode="$((8#$(stat_mode "${path}")))"
    if (((mode & 077) != 0)); then
      reasons+=("unsafe_gcloud_credential_store_permissions")
    fi
  }

  validate_gcloud_metadata_file() {
    validate_regular_current_user_file "$1" "config_metadata"
  }

  validate_known_adc_json() {
    local path="$1"
    [[ -f "${path}" && ! -L "${path}" ]] || return 0
    if jq -e '
      (.type == "service_account")
      or (
        (.type == "external_account")
        and (
          has("private_key")
          or has("private_key_id")
          or (tostring | test("-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"))
        )
      )
      or has("private_key")
      or has("private_key_id")
      or ((.private_key? // "") | test("-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"))
    ' "${path}" >/dev/null 2>&1; then
      reasons+=("unsafe_gcloud_adc_service_account_key_material")
    fi
  }

  is_structured_credential_candidate() {
    local path="$1"
    case "${path}" in
      *.json | *.db | *.key | *.p12 | *.pem)
        return 0
        ;;
      *)
        case "$(basename "${path}")" in
          *credential* | *Credential* | *token* | *Token* | *key* | *Key*)
            return 0
            ;;
          *)
            return 1
            ;;
        esac
        ;;
    esac
  }

  known_gcloud_stores="${TMP_DIR}/gcloud-known-stores.txt"
  find "${gcloud_config_dir}" \( \
      -name "credentials.db" -o \
      -name "access_tokens.db" -o \
      -name "application_default_credentials.json" -o \
      -name "adc.json" -o \
      -path "${gcloud_config_dir}/active_config" -o \
      -path "${gcloud_config_dir}/.last_update_check" -o \
      -path "${gcloud_config_dir}/.last_update_check.json" -o \
      -path "${gcloud_config_dir}/configurations/config_*" \
    \) -print >"${known_gcloud_stores}" 2>/dev/null || true
  while IFS= read -r known_store; do
    if is_strict_gcloud_credential_store "${known_store}"; then
      validate_strict_gcloud_credential_store "${known_store}"
      case "${known_store}" in
        */application_default_credentials.json | */adc.json)
          validate_known_adc_json "${known_store}"
          ;;
      esac
    elif is_gcloud_metadata_file "${known_store}"; then
      validate_gcloud_metadata_file "${known_store}"
    fi
  done <"${known_gcloud_stores}"

  key_scan_path="${TMP_DIR}/gcloud-key-filename-scan.txt"
  find "${gcloud_config_dir}" \( -name "*.p12" -o -name "*.pem" -o -iname "*service*account*key*.json" -o -iname "*service_account*key*.json" -o -iname "*key*.json" \) -print >"${key_scan_path}" 2>"${TMP_DIR}/gcloud-key-filename-scan.stderr" || true
  if grep -Ev '(/application_default_credentials\.json$|/adc\.json$|/\.last_update_check\.json$|/access_tokens\.db$|/credentials\.db$|/configurations/config_[^/]+$|/active_config$|/site-packages/|/__pycache__/)' "${key_scan_path}" >/dev/null; then
    reasons+=("possible_persisted_service_account_key_filename")
  fi

  gcloud_content_scan="${TMP_DIR}/gcloud-credential-content-scan.txt"
  : >"${gcloud_content_scan}"
  while IFS= read -r -d '' gcloud_file; do
    if is_known_gcloud_store "${gcloud_file}"; then
      continue
    fi
    if is_trusted_gcloud_installed_code_or_cache "${gcloud_file}"; then
      continue
    fi
    if is_structured_credential_candidate "${gcloud_file}"; then
      if grep -IaE -- "${GCLOUD_STRUCTURED_SECRET_CONTENT_PATTERN}" "${gcloud_file}" >/dev/null 2>&1; then
        printf '%s\n' "${gcloud_file}" >>"${gcloud_content_scan}"
      fi
      continue
    fi
    if grep -IqE -- "${GCLOUD_TEXT_SECRET_CONTENT_PATTERN}" "${gcloud_file}" 2>/dev/null; then
      printf '%s\n' "${gcloud_file}" >>"${gcloud_content_scan}"
    fi
  done < <(find "${gcloud_config_dir}" -type f -print0 2>/dev/null)
  if [[ -s "${gcloud_content_scan}" ]]; then
    reasons+=("possible_persisted_gcloud_credential_or_account_content")
  fi
else
  warnings+=("gcloud_config_directory_missing")
fi

artifact_content_scan="${TMP_DIR}/artifact-sensitive-content-scan.txt"
find "${ARTIFACT_DIR}" -maxdepth 1 -type f -print0 2>/dev/null |
  xargs -0 grep -IhE -- "${PUBLIC_EVIDENCE_SENSITIVE_CONTENT_PATTERN}" >"${artifact_content_scan}" 2>/dev/null || true
if [[ -s "${artifact_content_scan}" ]]; then
  reasons+=("generated_artifact_sensitive_content_detected")
fi

reason_json="$(json_string_array ${reasons[@]+"${reasons[@]}"})"
warning_json="$(json_string_array ${warnings[@]+"${warnings[@]}"})"

readiness_tmp="$(private_temp_file "readiness.json")"
jq -n \
  --arg schema_version "p176.gcp.reviewed_preflight_readiness.v1" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg expected_project_id_status "$(if [[ -z "${expected_project}" ]]; then printf 'missing'; elif [[ "${expected_project}" =~ ^opscat-p176-live-[a-z0-9-]{6,20}$ ]]; then printf 'p176_dedicated'; else printf 'invalid'; fi)" \
  --arg declared_project_id_present "$(if [[ -n "${declared_project}" ]]; then printf 'true'; else printf 'false'; fi)" \
  --arg active_project_status "$(if [[ -z "${active_project}" ]]; then printf 'unset'; else active_status='not_forbidden'; for forbidden in "${forbidden_projects[@]}"; do if [[ "${active_project}" == *"${forbidden}"* ]]; then active_status='forbidden'; fi; done; printf '%s' "${active_status}"; fi)" \
  --argjson billing_visible "${billing_visible}" \
  --argjson reasons "${reason_json}" \
  --argjson warnings "${warning_json}" \
  --argjson terraform_version "$(redacted_receipt "${terraform_version}")" \
  --argjson terraform_fmt "$(redacted_receipt "${terraform_fmt}")" \
  --argjson terraform_validate "$(redacted_receipt "${terraform_validate}")" \
  --argjson gcloud_version "$(redacted_receipt "${gcloud_version}")" \
  --argjson gcloud_config "$(redacted_receipt "${gcloud_config}")" \
  --argjson gcloud_auth "$(redacted_receipt "${gcloud_auth}")" \
  --argjson gcloud_billing "$(redacted_receipt "${gcloud_billing}")" \
  '{
    schema_version: $schema_version,
    generated_at: $generated_at,
    status: (if ($reasons | length) == 0 then "ready_for_plan_generation" else "blocked_external_gate" end),
    mutation_count: 0,
    apply_attempted: false,
    destroy_attempted: false,
    expected_project_id_status: $expected_project_id_status,
    declared_project_id_present: ($declared_project_id_present == "true"),
    active_gcloud_project_status: $active_project_status,
    billing_account_visible_open: $billing_visible,
    blocking_reasons: $reasons,
    warnings: $warnings,
    checks: {
      terraform_version: $terraform_version,
      terraform_fmt: $terraform_fmt,
      terraform_validate: $terraform_validate,
      gcloud_version: $gcloud_version,
      gcloud_config: $gcloud_config,
      gcloud_auth: $gcloud_auth,
      gcloud_billing_accounts: $gcloud_billing
    }
  }' >"${readiness_tmp}"
install_artifact "${readiness_tmp}" "${READINESS_JSON}"

if [[ "$(jq -r '.status' "${READINESS_JSON}")" != "ready_for_plan_generation" ]]; then
  boundary_tmp="$(private_temp_file "boundary.json")"
  logical_readiness_path="$(logical_path "${READINESS_JSON}")"
  jq -n \
    --arg schema_version "p176.gcp.reviewed_preflight_boundary.v1" \
    --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg readiness_path "${logical_readiness_path}" \
    --argjson reasons "${reason_json}" \
    '{
      schema_version: $schema_version,
      generated_at: $generated_at,
      status: "blocked_external_gate",
      boundary: "real Terraform plan not produced",
      readiness_path: $readiness_path,
      blocking_reasons: $reasons,
      mutation_count: 0,
      apply_attempted: false,
      destroy_attempted: false,
      next_required_gate: "Bind the externally provisioned opscat-p176-live-* project ID in terraform.tfvars and EXPECTED_PROJECT_ID, confirm active gcloud project is not forbidden, and confirm billing/quota authority before generating a reviewed plan."
    }' >"${boundary_tmp}"
  install_artifact "${boundary_tmp}" "${BOUNDARY_JSON}"
else
  assert_no_symlink_target "${BOUNDARY_JSON}"
  rm -f -- "${BOUNDARY_JSON}"
fi

if [[ "${RUN_PLAN}" == "1" && "$(jq -r '.status' "${READINESS_JSON}")" == "ready_for_plan_generation" ]]; then
  terraform -chdir="${SCRIPT_DIR}" plan -refresh=false -var-file="${TFVARS_FILE}" -out="p176-live.tfplan"
  terraform -chdir="${SCRIPT_DIR}" show -json "p176-live.tfplan" >"${SCRIPT_DIR}/p176-live.tfplan.json"
  jq -e --arg project "${expected_project}" \
    --arg billing_account "${EXPECTED_BILLING_ACCOUNT_ID}" \
    '.variables.project_id.value == $project and .variables.billing_account_id.value == $billing_account' \
    "${SCRIPT_DIR}/p176-live.tfplan.json" >/dev/null
  jq -e --arg project "${expected_project}" -f "${SCRIPT_DIR}/verify-apply-plan.jq" "${SCRIPT_DIR}/p176-live.tfplan.json" >/dev/null
  shasum -a 256 "${SCRIPT_DIR}/p176-live.tfplan" >"${SCRIPT_DIR}/p176-live.tfplan.sha256"
  PLAN_GENERATED_THIS_RUN=true
fi

plan_sha=""
plan_json_sha=""
if [[ "${PLAN_GENERATED_THIS_RUN}" == "true" ]]; then
  plan_sha="$(sha256_value "${SCRIPT_DIR}/p176-live.tfplan")"
  plan_json_sha="$(sha256_value "${SCRIPT_DIR}/p176-live.tfplan.json")"
fi
readiness_sha="$(sha256_value "${READINESS_JSON}")"
boundary_sha="$(sha256_value "${BOUNDARY_JSON}")"
procedure_sha="$(sha256_value "${PLAN_PROCEDURE_MD}")"
logical_readiness_path="$(logical_path "${READINESS_JSON}")"
logical_boundary_path="$(logical_path "${BOUNDARY_JSON}")"
logical_procedure_path="$(logical_path "${PLAN_PROCEDURE_MD}")"
logical_plan_path="$(logical_path "${SCRIPT_DIR}/p176-live.tfplan")"
logical_plan_json_path="$(logical_path "${SCRIPT_DIR}/p176-live.tfplan.json")"

receipts_tmp="$(private_temp_file "receipts.json")"
jq -n \
  --arg schema_version "p176.gcp.reviewed_preflight_receipts.v1" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg readiness_path "${logical_readiness_path}" \
  --arg readiness_sha "${readiness_sha}" \
  --arg boundary_path "${logical_boundary_path}" \
  --arg boundary_sha "${boundary_sha}" \
  --arg procedure_path "${logical_procedure_path}" \
  --arg procedure_sha "${procedure_sha}" \
  --arg plan_path "${logical_plan_path}" \
  --arg plan_sha "${plan_sha}" \
  --arg plan_json_path "${logical_plan_json_path}" \
  --arg plan_json_sha "${plan_json_sha}" \
  '{
    schema_version: $schema_version,
    generated_at: $generated_at,
    mutation_count: 0,
    receipts: {
      readiness: {path: $readiness_path, sha256: $readiness_sha},
      blocked_boundary: (if $boundary_sha == "" then null else {path: $boundary_path, sha256: $boundary_sha} end),
      plan_generation_procedure: {path: $procedure_path, sha256: $procedure_sha},
      reviewed_plan: (if $plan_sha == "" then null else {path: $plan_path, sha256: $plan_sha} end),
      reviewed_plan_json: (if $plan_json_sha == "" then null else {path: $plan_json_path, sha256: $plan_json_sha} end)
    }
  }' >"${receipts_tmp}"
install_artifact "${receipts_tmp}" "${RECEIPTS_JSON}"

echo "P176 preflight readiness: $(jq -r '.status' "${READINESS_JSON}")"
echo "Readiness: $(logical_path "${READINESS_JSON}")"
echo "Receipts: $(logical_path "${RECEIPTS_JSON}")"
if [[ -f "${BOUNDARY_JSON}" ]]; then
  echo "Boundary: $(logical_path "${BOUNDARY_JSON}")"
  exit 2
fi
