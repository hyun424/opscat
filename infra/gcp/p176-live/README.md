# P176 Live GCP Disposable Lab Infrastructure

This Terraform module implements P176-LIVE-001 only. It consumes the existing
`opscat-p176-live-*` GCP project created by `../p176-cost-cutoff` and does not
run the P176 live campaign or emit release evidence.

The module clones P174's disposable-project controls and tightens them for the
P176 live-lab contract:

- reviewed project ID from the cost-cutoff foundation;
- billing account binding and external admin topic recorded as reviewed inputs;
- owner, purpose, ticket, expiry, and expected-prefix labels;
- private VPC/subnet with no VM external IPs;
- subnet-scoped, auto-allocated Cloud NAT with error-only logging;
- explicit web/DNS-only VM egress followed by a deny-all egress rule;
- IAP/OS Login-only administration;
- private observer-to-target traffic only;
- target, observer, and harness-fault service accounts;
- no service-account keys;
- no IAM grant for the optional OpsCat principal;
- container metadata blocking on both hosts;
- saved reviewed apply and saved reviewed teardown plans.

The lab project, project services, and KRW budget are owned by
`../p176-cost-cutoff`; this root must not declare `google_project`,
`google_project_service`, `google_billing_budget`, `data.google_project`, or
project deletion.

The NAT exists because both startup scripts install Docker from upstream package
repositories. Runtime egress remains restricted to TCP 53/80/443 and UDP 53;
all other VM egress is denied. VM creation depends on the NAT and both egress
firewall rules, so paid compute cannot start before the bounded path exists. The
deploy verifier rejects project ownership, service enablement, budget resources,
static external addresses, public VM interfaces, unexpected egress rules, and
plans without the single reviewed router/NAT pair.

## Use

Copy `terraform.tfvars.example` to `terraform.tfvars`, choose a fresh
`opscat-p176-live-*` project ID from the cost-cutoff foundation, and set
`EXPECTED_PROJECT_ID` to the same value. Keep billing and account identifiers
only in local uncommitted configuration.

```bash
terraform -chdir=infra/gcp/p176-live fmt -check
terraform -chdir=infra/gcp/p176-live init
terraform -chdir=infra/gcp/p176-live validate
EXPECTED_PROJECT_ID=opscat-p176-live-<fresh-suffix> \
EXPECTED_BILLING_ACCOUNT_ID=<billing-account-id> \
infra/gcp/p176-live/deploy.sh
```

`deploy.sh` writes `p176-live.tfplan`, `p176-live.tfplan.json`, and
`p176-live.tfplan.sha256`, then exits. Review the JSON plan before applying the
exact saved plan:

```bash
APPLY_REVIEWED_PLAN=1 \
EXPECTED_PROJECT_ID=opscat-p176-live-<fresh-suffix> \
EXPECTED_BILLING_ACCOUNT_ID=<billing-account-id> \
EXPECTED_PLAN_SHA256=<reviewed-plan-sha256> \
infra/gcp/p176-live/deploy.sh
```

For teardown, keep the same `terraform.tfvars`, `EXPECTED_PROJECT_ID`, and
`EXPECTED_BILLING_ACCOUNT_ID`:

```bash
EXPECTED_PROJECT_ID=opscat-p176-live-<fresh-suffix> \
EXPECTED_BILLING_ACCOUNT_ID=<billing-account-id> \
infra/gcp/p176-live/destroy.sh
```

The destroy script writes a saved destroy plan and verifies it is a delete-only
plan for the frozen project before any reviewed apply:

```bash
APPLY_REVIEWED_DESTROY=1 \
EXPECTED_PROJECT_ID=opscat-p176-live-<fresh-suffix> \
EXPECTED_BILLING_ACCOUNT_ID=<billing-account-id> \
EXPECTED_PLAN_SHA256=<reviewed-destroy-plan-sha256> \
infra/gcp/p176-live/destroy.sh
```

Do not execute apply or destroy from automation without a human-reviewed plan
digest. P176 live release evidence remains owned by the existing P176 release
path; this module only provides the disposable cloud boundary for later live-lab
tickets.
