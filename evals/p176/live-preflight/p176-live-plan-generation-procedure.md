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
