#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/opscat-p176-uv-cache}"
mkdir -p "$UV_CACHE_DIR"

python_sources=(
  app/services/p175_live_release.py
  app/services/p176_action_eligibility.py
  app/services/p176_campaign.py
  app/services/p176_contracts.py
  app/services/p176_evaluator.py
  app/services/p176_evidence.py
  app/services/p176_live_bridge.py
  app/services/p176_live_gates.py
  app/services/p176_release.py
  scripts/finalize_p175_live_release.py
  scripts/run_p176_live_bridge.py
  scripts/run_p176_live_qualification.py
  scripts/run_p176_qualification.py
  tests/test_p175_live_release.py
  tests/test_p176_action_eligibility.py
  tests/test_p176_campaign.py
  tests/test_p176_contracts.py
  tests/test_p176_cost_cutoff.py
  tests/test_p176_evaluator.py
  tests/test_p176_evidence.py
  tests/test_p176_live_bridge.py
  tests/test_p176_live_campaign.py
  tests/test_p176_live_gates.py
  tests/test_p176_live_infra_plan.py
  tests/test_p176_live_release.py
  tests/test_p176_live_topology.py
  tests/test_p176_release.py
  tests/test_p176_runner.py
)

live_sources=(
  infra/gcp/p176-live/.terraform.lock.hcl
  infra/gcp/p176-live/README.md
  infra/gcp/p176-live/deploy.sh
  infra/gcp/p176-live/destroy.sh
  infra/gcp/p176-live/main.tf
  infra/gcp/p176-live/observer-startup.sh
  infra/gcp/p176-live/outputs.tf
  infra/gcp/p176-live/preflight.sh
  infra/gcp/p176-live/target-startup.sh
  infra/gcp/p176-live/terraform.tfvars.example
  infra/gcp/p176-live/terraform.tfvars.template
  infra/gcp/p176-live/variables.tf
  infra/gcp/p176-live/verify-apply-plan.jq
  infra/gcp/p176-live/verify-destroy-plan.jq
  infra/gcp/p176-live/versions.tf
  lab/p176/live/docker-compose.yml
  lab/p176/live/service_stub.py
  lab/p176/live/topology.json
)

cost_cutoff_sources=(
  infra/gcp/p176-cost-cutoff/.terraform.lock.hcl
  infra/gcp/p176-cost-cutoff/README.md
  infra/gcp/p176-cost-cutoff/deploy.sh
  infra/gcp/p176-cost-cutoff/destroy.sh
  infra/gcp/p176-cost-cutoff/main.tf
  infra/gcp/p176-cost-cutoff/outputs.tf
  infra/gcp/p176-cost-cutoff/preflight.sh
  infra/gcp/p176-cost-cutoff/terraform.tfvars.example
  infra/gcp/p176-cost-cutoff/terraform.tfvars.template
  infra/gcp/p176-cost-cutoff/variables.tf
  infra/gcp/p176-cost-cutoff/verify-apply-plan.jq
  infra/gcp/p176-cost-cutoff/verify-destroy-plan.jq
  infra/gcp/p176-cost-cutoff/versions.tf
)

terraform_modules=(
  infra/gcp/p176-live
  infra/gcp/p176-cost-cutoff
)

terraform_validate() {
  local module="$1"
  local plugin_dir="$ROOT_DIR/$module/.terraform/providers"
  local tf_data_dir
  local status=0
  tf_data_dir="$(mktemp -d "${TMPDIR:-/tmp}/opscat-p176-tfdata.XXXXXX")"
  (
    export TF_DATA_DIR="$tf_data_dir"
    if [[ -d "$plugin_dir" ]]; then
      terraform -chdir="$module" init -backend=false -input=false -plugin-dir="$plugin_dir"
    else
      terraform -chdir="$module" init -backend=false -input=false
    fi
    terraform -chdir="$module" validate
  ) || status=$?
  rm -rf "$tf_data_dir"
  return "$status"
}

validate_live_apply_guard() {
  local plan_json="$1"
  local project
  project="$(jq -er '.variables.project_id.value' "$plan_json")"
  jq -e --arg project "$project" -f infra/gcp/p176-live/verify-apply-plan.jq "$plan_json" >/dev/null
}

validate_live_destroy_guard() {
  local plan_json="$1"
  local project
  project="$(jq -er '.variables.project_id.value' "$plan_json")"
  jq -e --arg project "$project" -f infra/gcp/p176-live/verify-destroy-plan.jq "$plan_json" >/dev/null
}

validate_cost_cutoff_apply_guard() {
  local plan_json="$1"
  local admin_project
  local lab_project
  admin_project="$(jq -er '.variables.admin_project_id.value' "$plan_json")"
  lab_project="$(jq -er '.variables.lab_project_id.value' "$plan_json")"
  jq -e \
    --arg admin_project "$admin_project" \
    --arg lab_project "$lab_project" \
    -f infra/gcp/p176-cost-cutoff/verify-apply-plan.jq \
    "$plan_json" >/dev/null
}

validate_cost_cutoff_destroy_guard() {
  local plan_json="$1"
  local admin_project
  local lab_project
  admin_project="$(jq -er '.variables.admin_project_id.value' "$plan_json")"
  lab_project="$(jq -er '.variables.lab_project_id.value' "$plan_json")"
  jq -e \
    --arg admin_project "$admin_project" \
    --arg lab_project "$lab_project" \
    -f infra/gcp/p176-cost-cutoff/verify-destroy-plan.jq \
    "$plan_json" >/dev/null
}

validate_preserved_plan_guards() {
  local live_apply_plan="infra/gcp/p176-live/.terraform/g001-preflight/p176-live.tfplan.json"
  local live_destroy_plan="infra/gcp/p176-live/.terraform/g001-preflight/p176-live-destroy.tfplan.json"
  local cost_apply_plan="infra/gcp/p176-cost-cutoff/.terraform/g001-preflight/p176-cost-cutoff.tfplan.json"
  local cost_destroy_plan="infra/gcp/p176-cost-cutoff/.terraform/g001-preflight/p176-cost-cutoff-destroy.tfplan.json"

  if [[ -f "$live_apply_plan" ]]; then
    validate_live_apply_guard "$live_apply_plan"
  fi
  if [[ -f "$live_destroy_plan" ]]; then
    validate_live_destroy_guard "$live_destroy_plan"
  fi
  if [[ -f "$cost_apply_plan" ]]; then
    validate_cost_cutoff_apply_guard "$cost_apply_plan"
  fi
  if [[ -f "$cost_destroy_plan" ]]; then
    validate_cost_cutoff_destroy_guard "$cost_destroy_plan"
  fi
}

for source in "${python_sources[@]}" "${live_sources[@]}" "${cost_cutoff_sources[@]}"; do
  test -f "$source"
done

uv run --no-sync --extra dev pytest -q \
  tests/test_p175_live_release.py \
  tests/test_p176_action_eligibility.py \
  tests/test_p176_campaign.py \
  tests/test_p176_contracts.py \
  tests/test_p176_cost_cutoff.py \
  tests/test_p176_evaluator.py \
  tests/test_p176_evidence.py \
  tests/test_p176_live_bridge.py \
  tests/test_p176_live_campaign.py \
  tests/test_p176_live_gates.py \
  tests/test_p176_live_infra_plan.py \
  tests/test_p176_live_release.py \
  tests/test_p176_live_topology.py \
  tests/test_p176_release.py \
  tests/test_p176_runner.py
uv run --no-sync --extra dev ruff check "${python_sources[@]}"
uv run --no-sync --extra dev mypy "${python_sources[@]}"
uv run --no-sync --extra dev python - <<'PY'
import json
from pathlib import Path

from app.services.p175_live_release import validate_release_evidence as validate_p175
from app.services.p176_campaign import generate_p176_campaign, generate_p176_sealed_truth
from app.services.p176_release import build_readiness_artifact

root = Path('.')
p175 = json.loads((root / 'evals/p175/output/release-evidence.json').read_text())
validate_p175(p175, project_root=root)
campaign = generate_p176_campaign()
manifest = json.loads((root / 'evals/p176/input/manifest.json').read_text())
truth = json.loads((root / manifest['sealed_truth_path']).read_text())
assert manifest['campaign_hash'] == campaign['campaign_hash']
assert truth == generate_p176_sealed_truth(campaign)
readiness = json.loads((root / 'evals/p176/output/readiness-not-executed.json').read_text())
assert readiness == build_readiness_artifact(project_root=root)
PY
bash -n infra/gcp/p176-live/deploy.sh
bash -n infra/gcp/p176-live/destroy.sh
bash -n infra/gcp/p176-live/observer-startup.sh
bash -n infra/gcp/p176-live/preflight.sh
bash -n infra/gcp/p176-live/target-startup.sh
bash -n infra/gcp/p176-cost-cutoff/deploy.sh
bash -n infra/gcp/p176-cost-cutoff/destroy.sh
bash -n infra/gcp/p176-cost-cutoff/preflight.sh
bash -n scripts/verify_p176.sh
jq --arg project "opscat-p176-live-placeholder" -f infra/gcp/p176-live/verify-apply-plan.jq /dev/null >/dev/null
jq --arg project "opscat-p176-live-placeholder" -f infra/gcp/p176-live/verify-destroy-plan.jq /dev/null >/dev/null
jq --arg admin_project "opscat-p176-admin-placeholder" \
  --arg lab_project "opscat-p176-live-placeholder" \
  -f infra/gcp/p176-cost-cutoff/verify-apply-plan.jq /dev/null >/dev/null
jq --arg admin_project "opscat-p176-admin-placeholder" \
  --arg lab_project "opscat-p176-live-placeholder" \
  -f infra/gcp/p176-cost-cutoff/verify-destroy-plan.jq /dev/null >/dev/null
validate_preserved_plan_guards
for module in "${terraform_modules[@]}"; do
  terraform -chdir="$module" fmt -check
  terraform_validate "$module"
done
git diff --check
