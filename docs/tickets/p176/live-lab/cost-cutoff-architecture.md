# P176 Cost Cutoff Architecture

The P176 cost-cutoff control plane runs outside the disposable lab. The cost-cutoff Terraform foundation creates exactly two fresh projects under the same locally supplied organization and billing IDs: a dedicated `opscat-p176-admin-*` admin project and a separate disposable `opscat-p176-live-*` lab project. Both projects are created with `auto_create_network=false` and `deletion_policy=DELETE`. The foundation owns the lab billing budget and references `google_project.lab.number` inside the same plan while publishing notifications to the admin topic. The live Terraform root consumes the existing lab project ID, billing binding, and admin topic as reviewed inputs; it must not own `google_project`, project service enablement, billing budget, project number lookup, or project deletion. The controller must not run inside the lab project and must never target an existing shared, production, live, or lab-hosted controller project.

Budgets are not hard caps. Google Cloud budget notifications can arrive late or be skipped, so this design is a fail-closed compensating control, not a spending guarantee. External authorization is required before deploy or destroy; this external authorization means operators must review the saved Terraform plan JSON and bind the exact SHA-256 digest before any apply.

Flow:

1. The lab budget is set to 30,000 KRW and publishes to the external admin-project Pub/Sub topic.
2. Eventarc routes budget messages to the Workflow as Pub/Sub CloudEvents.
3. The Workflow decodes Base64 from `event.data.message.data`, JSON-parses the budget provider payload, and requires `costAmount`, `budgetAmount`, and `currencyCode` before any durable write.
4. The required amounts must be nonnegative JSON numbers and `currencyCode` must be `KRW`; malformed, missing, negative, string-typed, or wrong-currency messages are rejected without writing zero defaults.
5. `forecastAmount` is optional and contributes to the conservative threshold only when it is also a nonnegative JSON number.
6. Budget/provider events atomically update the canonical `state/latest.json` receipt with a GCS generation precondition and preserve a minimal immutable provider-state receipt.
7. Cloud Scheduler invokes the Workflow every 5 minutes as a timer only; it does not send fake `cost=0`.
8. Timer invocations read the last durable budget/provider state receipt and hard-stop if it is missing or stale after 600 seconds.
9. Fresh state is evaluated conservatively as `max(actual, forecast * 1.15)` whenever valid forecast data is available.
10. The Workflow creates a GCS lease object with `ifGenerationMatch: 0` for in-progress dedupe/idempotency.
11. Duplicate lease executions inspect the terminal receipt and return only when terminal success already exists; otherwise they retry the idempotent stop/disable sequence.
12. At 24,000 KRW effective spend, the Workflow performs a soft stop by stopping lab compute.
13. At 27,000 KRW effective spend, the Workflow performs the hard cutoff: stop compute before disabling billing.
14. Terminal receipts expire after 36 hours, and the absolute lease is 48 hours.

Apply order is `infra/gcp/p176-cost-cutoff` first, then `infra/gcp/p176-live` after reviewing the exported lab project ID and admin topic. Destroy order is the reverse: destroy live resources first, then destroy the cost-cutoff foundation so the lab project and budget are deleted only by the foundation state.

The receipt bucket stores minimal immutable receipts only. It has uniform bucket-level access, public access prevention, versioning, a locked retention policy, and lifecycle deletion after two days.

IAM is split across dedicated Workflow, Eventarc, and Scheduler service accounts. The Workflow gets only log writing, object creation/read access for minimal receipts, and a custom external lab-only project role containing the exact permissions needed to list/stop compute and detach billing. The design rejects wildcard IAM, owner/editor, service-account keys, org/folder IAM, shared VPC or production project patterns, lab-hosted controller patterns, public access, and any OpsCat mutation grants.
