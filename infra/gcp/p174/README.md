# P174 GCP Disposable Lab Infrastructure

This Terraform module creates the P174 infrastructure foundation only:

- a dedicated new GCP project under a locally supplied organization ID;
- billing attachment to a locally supplied billing account ID;
- a `250000` KRW budget alert;
- a private VPC/subnet;
- IAP SSH-only administration;
- private observer-to-target traffic;
- target `e2-standard-8` and observer `e2-standard-2` VMs in `asia-northeast3-a`;
- separate target and observer VM service accounts.

Service-account keys are intentionally not created. Administration uses attached
service accounts, OS Login, and IAP tunneling.

Containers do not receive per-container GCP identities. Application capability
separation is enforced by the P174 workload contract and container runtime
configuration, while both VM startup scripts install a persistent `DOCKER-USER`
rule that blocks container access to the GCP metadata IP `169.254.169.254`
without blocking host metadata access.

## Use

Copy `terraform.tfvars.example` to `terraform.tfvars`, choose a fresh
`opscat-p174-*` project ID, fill the local-only organization and billing
values, and set `EXPECTED_PROJECT_ID` to the same project value.

```bash
terraform -chdir=infra/gcp/p174 fmt -check
terraform -chdir=infra/gcp/p174 init
terraform -chdir=infra/gcp/p174 validate
EXPECTED_PROJECT_ID=opscat-p174-example123 infra/gcp/p174/deploy.sh
```

`deploy.sh` saves and applies a reviewed plan only after checking that the
expected project ID matches the Terraform variables and is not a forbidden
existing project. Do not run it against any non-P174 project.

For teardown, keep the same `terraform.tfvars` and `EXPECTED_PROJECT_ID`:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 infra/gcp/p174/destroy.sh
```

The destroy script checks the expected project ID, forbidden project list,
Terraform variables, and state output before creating a destroy plan and
prompting for confirmation.
