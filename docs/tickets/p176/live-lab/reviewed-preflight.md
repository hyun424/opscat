# P176 GCP Reviewed-Preflight Preparation

P176 preflight is local, read-only, and fail-closed. It may inspect local
`gcloud` and Terraform readiness, confirm that the frozen billing account and
reviewed externally provisioned lab project inputs are bound, validate the
Terraform module, and generate redacted receipts. It must not run
`terraform apply`, `terraform destroy`, create projects, enable APIs, attach
billing, or persist raw `gcloud` payloads, account identifiers, billing
identifiers, organization identifiers, or credential contents in generated
artifacts.

## Nonsecret Configuration Template

Use `infra/gcp/p176-live/terraform.tfvars.template` as the source template:

```hcl
billing_account_id = "<gcp-billing-account-id>"
project_id         = "opscat-p176-live-<fresh-suffix>"
ssh_admin_members  = ["user:<iap-oslogin-admin-email>"]
opscat_principal   = ""

cost_cutoff_budget_topic_name = "projects/opscat-p176-admin-<fresh-suffix>/topics/p176-cost-cutoff-budget"
```

The concrete `terraform.tfvars` remains local-only and must not be committed.

## Preflight Command

Default mode writes readiness, boundary, procedure, and digest receipts without
attempting a Terraform plan:

```bash
EXPECTED_PROJECT_ID=<fresh opscat-p176-live-* project> \
EXPECTED_BILLING_ACCOUNT_ID=<billing account id from local tfvars> \
infra/gcp/p176-live/preflight.sh
```

Plan-generation mode is still plan-only and only runs when readiness is clean:

```bash
EXPECTED_PROJECT_ID=<fresh opscat-p176-live-* project> \
EXPECTED_BILLING_ACCOUNT_ID=<billing account id from local tfvars> \
P176_PREFLIGHT_RUN_PLAN=1 \
infra/gcp/p176-live/preflight.sh
```

The script writes minimized artifacts under `evals/p176/live-preflight/` by default:

- `p176-live-preflight-readiness.json`
- `p176-live-preflight-boundary.json` when blocked
- `p176-live-preflight-receipts.json`
- `p176-live-plan-generation-procedure.md`

If Terraform produces `p176-live.tfplan`, the script also verifies
`p176-live.tfplan.json` with `verify-apply-plan.jq` and records only SHA-256
digests in the preflight receipt.

## External Gate

A real reviewed plan is blocked until all of these are true:

- `terraform.tfvars` binds an existing `opscat-p176-live-*` lab project ID created by `infra/gcp/p176-cost-cutoff`.
- `EXPECTED_PROJECT_ID` matches that reviewed input.
- Active `gcloud` project is not a forbidden existing project.
- The frozen billing account configured outside generated artifacts is visible and open.
- Terraform `fmt -check` and `validate` pass.
- No persisted service-account key filename or credential/account-like content is detected by the preflight scan.
- Generated artifact content scans clean for credential, secret, account, billing, and organization patterns.

When any gate is missing, the boundary artifact records
`status = "blocked_external_gate"` and `mutation_count = 0`.
