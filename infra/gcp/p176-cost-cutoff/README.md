# P176 Cost Cutoff Control Plane

This module defines the out-of-band cost-cutoff controller for the disposable P176 live lab. It creates exactly two fresh projects under locally supplied `org_id` and `billing_account_id` values: a non-lab `opscat-p176-admin-*` admin project and a separate `opscat-p176-live-*` lab project. It also owns the lab billing budget and email notification channel. It must never target an existing, shared, production, live, or lab-hosted controller project.

Both projects are created with `auto_create_network=false` and `deletion_policy=DELETE`. Terraform enables only the services declared in `local.required_admin_services` and `local.required_lab_services`; no shared VPC, org/folder IAM, public access, owner/editor roles, service-account keys, or ad hoc `gcloud` mutation is allowed.

The module is plan-first. `preflight.sh`, `deploy.sh`, and `destroy.sh` refuse unsafe project names, generate plans with `-refresh=false`, require reviewed plan JSON through jq guards, and apply only an exact reviewed plan digest. They never call `gcloud projects create`, `gcloud services enable`, or use `--auto-approve`.

The lab budget references `google_project.lab.number` in the same foundation plan and publishes to the admin-project `budget_topic_name`. Eventarc delivers the real Pub/Sub CloudEvent envelope, so the Workflow decodes `event.data.message.data` from Base64, JSON-parses it, and requires nonnegative numeric `costAmount` and `budgetAmount` plus `currencyCode = "KRW"` before writing any durable state. Optional `forecastAmount` is used only when it is also nonnegative numeric; otherwise malformed messages are rejected rather than defaulted to zero.

Budget/provider events persist the canonical latest state in GCS, while the Scheduler fallback is timer-only and never supplies a fake zero-cost value. Timer runs fail closed when the latest durable state is missing or older than 600 seconds, then use the latest durable effective amount before stopping compute and, for hard cutoff, detaching billing.
