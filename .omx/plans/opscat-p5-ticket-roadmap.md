# OpsCat P5 Ticket Roadmap — OSS-Usable Productization Without Auth

Status: planned
Owner: leader + team lanes for connector/platform/UI/QA/security review
Scope boundary: **Do not implement auth/OIDC/SSO/session login in P5**. Keep the existing local-header/demo identity boundary unless a later user request explicitly reopens auth.

## P5 objective

P5 turns the P4 portfolio-grade local/mock MVP into an open-source-usable product prototype without crossing into real auth work. The goal is to make OpsCat feel like an operations product a user could pay for in a controlled beta: real-feeling connector setup, permission previews, durable worker behavior, approval console, incident import surfaces, release evidence, and self-monitoring.

P5 must preserve P4 safety boundaries:

- no real production mutation by default;
- no broad provider credentials;
- no arbitrary shell product tool;
- no raw-log bulk ingestion;
- all connector/action failures escalate rather than failing silently;
- all external-write capabilities stay dry-run or explicit approval-gated previews.

## P5 definition of done

P5 is complete when:

- a new external user can clone, set up, run demo fixtures, inspect docs, and verify locally without credentials;
- every P5 ticket has a RED/GREEN test checkpoint;
- `bash scripts/verify.sh` passes;
- connector evals include setup/config/failure coverage beyond provider-call failures;
- a beta user can configure mock/fixture connectors, preview permissions, process imported incidents, approve/reject proposed actions, and read morning/release evidence without touching real production systems;
- production gaps remain explicit, especially auth being intentionally deferred.

## Explicit non-goal: auth

P5 does **not** include:

- OIDC/SSO;
- login/session UI;
- password auth;
- production user provisioning;
- RBAC redesign around authenticated principals;
- CSRF/session-hardening tied to browser mutation forms.

Existing tenant/workspace/role headers may remain as the demo identity mechanism. P5 can improve authorization checks around existing principals, but must not introduce an auth product surface.

## Ticket order

### P5-001 ✅ — Connector setup registry and permission preview

Goal: create a product-facing integration catalog that explains what each connector can do before any token/secret is entered.

Plan:
1. Add a connector catalog service/API returning connector name, capabilities, risk, read-only/write-like status, required secret names, required role, approval requirement, and dry-run support.
2. Add tests proving no broad credentials are requested and every capability has explicit risk/permission metadata.
3. Render the catalog in the operator/admin surface as a read-only setup guide.
4. Add docs explaining minimum permissions by connector.

Acceptance tests:
- Unknown connector/capability fails closed.
- Every registered capability appears in the catalog.
- Every capability includes `read_only`, `risk_level`, `required_role`, `requires_approval`, and `required_secret_name`.
- Catalog HTML/API contains no raw secret values.

Files likely touched:
- `app/connectors/*`
- `app/services/connector_service.py`
- `app/api/operator.py` or new `app/api/connectors.py`
- `tests/test_connector_catalog.py`
- `docs/connector-permissions.md`

### P5-002 ✅ — Local secret setup lifecycle and redaction audit

Goal: make secret handling look like a real product boundary while staying local/mock.

Plan:
1. Add secret lifecycle operations around the existing local encrypted secret provider: create/update/delete/list-metadata-only.
2. Store only metadata in list/read surfaces; never return plaintext secret values.
3. Add audit events for secret writes, rotations, deletions, missing-secret reads, and connector usage.
4. Add tests for redaction in audit logs and reports.

Acceptance tests:
- List secret metadata never exposes ciphertext or plaintext.
- Updating a secret changes usable connector behavior without leaking token text.
- Deleting a secret causes connector eval missing-credential fail-closed behavior.
- Audit logs show actor/scope/secret name but not secret value.

Files likely touched:
- `app/services/secret_service.py`
- `app/models/secret.py`
- `app/api/workspace.py` or new `app/api/secrets.py`
- `tests/test_secret_lifecycle.py`
- `docs/connector-permissions.md`

### P5-003 ✅ — Incident import adapters for realistic alert/event envelopes

Goal: move beyond hand-written mock alerts by accepting realistic Sentry/Datadog/Loki-like fixture envelopes while keeping them local.

Plan:
1. Add normalized `SignalEnvelope`/adapter layer for fixture alerts.
2. Support local fixture ingestion for at least Sentry-like issue, Datadog monitor, and Loki/log alert JSON samples.
3. Normalize to existing incident creation flow with idempotency/fingerprint behavior.
4. Add redaction before persistence/evidence creation.

Acceptance tests:
- Fixture envelopes normalize to tenant/workspace/scenario/service/environment/severity/fingerprint.
- Duplicate fixture delivery does not duplicate incidents/jobs.
- Secret-bearing fixture fields are redacted before evidence/report surfaces.
- Unsupported provider envelope fails closed with actionable error.

Files likely touched:
- `app/schemas/incidents.py`
- `app/services/incident_service.py`
- new `app/services/signal_normalizer.py`
- `tests/fixtures/signals/*.json`
- `tests/test_signal_normalizer.py`

### P5-004 ✅ — Durable worker CLI and dead-letter operations

Goal: make background workflow behavior operationally credible without deploying a real queue.

Plan:
1. Add a CLI for processing workflow jobs: process one, drain queue, show stats, retry failed, dead-letter stuck jobs.
2. Add bounded lease expiry/retry behavior tests.
3. Add dead-letter evidence/reporting so quiet failures are visible.
4. Include CLI in release verification as a smoke check.

Acceptance tests:
- CLI can drain N queued mock incidents deterministically.
- Failed jobs retry until max attempts then dead-letter/escalate.
- Stale leased jobs can be reclaimed safely.
- CLI exits non-zero on unrecoverable errors and writes actionable output.

Files likely touched:
- `app/services/workflow_service.py`
- `scripts/worker.py` or `scripts/workflow_cli.py`
- `tests/test_workflow_cli.py`
- `scripts/verify.sh`

### P5-005 ✅ — Approval console without auth/session work

Goal: build a useful operator approval console while keeping auth deferred.

Plan:
1. Extend server-rendered operator UI with read-only incident/action review and explicit API-based approve/reject instructions.
2. Optionally add POST approval endpoints already protected by existing header principal checks, but avoid browser forms/session/CSRF until auth is in scope.
3. Add action diff/preview rendering: what would happen, risk, policy, required evidence, post-checks.
4. Add browser-contract tests for pending approvals list and action detail.

Acceptance tests:
- Pending approval list shows only workspace-scoped actions.
- Action detail includes risk, policy decision, preconditions, post-checks, evidence IDs, and dry-run payload.
- Cross-workspace action detail returns 404.
- No unsafe browser mutation form is introduced.

Files likely touched:
- `app/api/operator.py`
- `app/services/action_service.py`
- `tests/test_operator_approval_console.py`
- `tests/test_operator_dashboard_e2e.py`

### P5-006 ✅ — Night Autopilot policy editor and morning report evidence

Goal: make “it helps while I sleep” concrete without letting it do dangerous things.

Plan:
1. Add local policy config for quiet-hours allowlist, max attempts, severity limits, and escalation recipients.
2. Add morning report generation from actual simulated incidents/actions.
3. Add tests for denied production/high-risk paths and allowed low-risk paths.
4. Add docs explaining safe overnight mode.

Acceptance tests:
- Low-risk allowlisted mock action can run in night simulation.
- High-risk/protected/production action is denied or escalated.
- Morning report includes detected/resolved/escalated counts, blocked actions, verification outcomes, follow-ups.
- Policy config changes are audited and scoped.

Files likely touched:
- `app/services/night_autopilot.py`
- `app/api/night_autopilot.py`
- `app/models/policy.py`
- `tests/test_night_autopilot_policy.py`
- `docs/wake-up-report.md`

### P5-007 ✅ — Connector eval expansion: setup, permission, and incident-import paths

Goal: expand P4 connector evals into product-readiness evals.

Plan:
1. Add connector catalog/setup eval cases.
2. Add secret lifecycle eval cases.
3. Add fixture incident import eval cases.
4. Emit combined Markdown evidence for connector readiness.

Acceptance tests:
- Connector eval total increases with non-provider-call setup cases.
- Eval report distinguishes provider failure, setup failure, permission mismatch, missing secret, idempotency replay, and import normalization.
- `scripts/verify.sh` includes the expanded runner.

Files likely touched:
- `scripts/run_connector_evals.py`
- `tests/test_connector_evals.py`
- `docs/eval-report.md`
- `docs/release-evidence.md`

### P5-008 ✅ — Self-observability for OpsCat itself

Goal: make OpsCat observable as an agentic operations system.

Plan:
1. Add internal metrics counters/snapshots for incidents created, jobs processed, actions proposed/executed/blocked, eval pass counts, connector failures, escalations.
2. Expose a local `/health` or `/metrics`-style JSON endpoint without adding a metrics dependency unless justified.
3. Add structured audit/timeline summaries for agent decisions.
4. Add docs explaining what a beta operator should monitor.

Acceptance tests:
- Metrics endpoint returns deterministic counters after test actions.
- Connector failures and escalations increment counters.
- Metrics contain no secret/PII values.
- Health output remains backwards compatible.

Files likely touched:
- `app/api/health.py`
- new `app/services/observability.py`
- `tests/test_self_observability.py`
- `docs/operations/self-observability.md`

### P5-009 ✅ — CI-ready verification profile

Goal: make the release gate easy to run in CI and durable for future AI teams.

Plan:
1. Split `scripts/verify.sh` into named profiles if needed: fast, full, eval, docs.
2. Add a GitHub Actions workflow or local CI spec that runs full verification without secrets.
3. Add tests/docs ensuring generated artifacts are controlled.
4. Keep Docker Compose config validation optional/fallback if CI lacks Docker.

Acceptance tests:
- Local `bash scripts/verify.sh` remains green.
- CI profile command is documented and does not require credentials.
- Eval outputs are generated in temp paths and not committed.
- Failure output tells future agents which gate failed.

Files likely touched:
- `scripts/verify.sh`
- `.github/workflows/ci.yml` if GitHub workflow is desired
- `docs/release-evidence.md`
- `tests/test_release_evidence_index.py`

### P5-010 ✅ — Beta onboarding and deployment dry-run guide

Goal: make the project understandable as a paid-beta candidate.

Plan:
1. Add a 10-minute beta walkthrough: configure fixture connector, import fixture incident, review action, approve/reject via API, read report, read morning report.
2. Add deployment dry-run guide for local Docker/Postgres and future hosted/self-hosted split.
3. Add permission model documentation that explicitly says auth is deferred.
4. Add “what would be required before real customer production use” checklist.

Acceptance tests:
- Docs tests verify README links to beta walkthrough, connector permissions, release evidence, and auth-deferred boundary.
- Commands in walkthrough are copy-paste runnable locally or explicitly marked illustrative.
- No doc claims production readiness.

Files likely touched:
- `README.md`
- `docs/beta-walkthrough.md`
- `docs/deployment-dry-run.md`
- `docs/paid-beta-readiness.md`
- `tests/test_beta_docs.py`

### P5-011 ✅ — Security/threat-model refresh without auth implementation

Goal: review P5 trust boundaries while respecting the auth exclusion.

Plan:
1. Update threat model for connector setup, secret lifecycle, incident import, worker CLI, approval console, and self-observability.
2. Add static/doc tests ensuring dangerous surfaces remain absent.
3. Add a P5 security review checklist.
4. Keep auth listed as deferred production prerequisite, not a P5 implementation task.

Acceptance tests:
- Threat model names every new P5 surface and mitigation.
- Test asserts no product tool exposes arbitrary shell/cloud/Kubernetes/database mutation.
- Docs state auth is deferred and demo identity is not production auth.

Files likely touched:
- `docs/threat-model.md`
- `docs/paid-beta-readiness.md`
- `tests/test_security_boundaries.py`

### P5-012 ✅ — P5 final release evidence and hardening

Goal: close P5 only after full release evidence is green and docs match behavior.

Plan:
1. Run full verification.
2. Update release evidence index with P5 artifacts.
3. Update integration verification with exact PASS evidence.
4. Review git diff for generated artifacts, secret leakage, and overclaims.
5. Commit with Lore protocol.

Acceptance tests:
- `bash scripts/verify.sh` PASS.
- P5 docs and tests all pass.
- `git status --short` contains only intentional changes before final commit and clean after commit.

Files likely touched:
- `docs/release-evidence.md`
- `docs/integration-verification.md`
- `.omx/plans/opscat-p5-ticket-roadmap.md`
- `docs/operations/p5-ticket-roadmap.md`

## Current P5 progress
- P5-001: completed with `/connectors` permission preview API and `docs/connector-permissions.md`.
- P5-002: completed with metadata-only secret lifecycle API and audit-safe redaction tests.
- P5-003: completed with fixture signal normalization for Sentry/Datadog/Loki/generic envelopes.
- P5-004: completed with `scripts/workflow_cli.py` stats/drain/dead-letter local worker operations.
- P5-005: completed with scoped pending approval list and action preview pages without browser mutation forms.
- P5-006: completed with scoped policy audit API, safe overnight escalation gates, and morning report evidence.
- P5-007: completed with connector setup/permission/secret/import-normalization eval scenarios and release evidence.
- P5-008: completed with scoped `/metrics` counters and self-observability docs.
- P5-009: completed with named verify profiles and secret-free GitHub Actions full verification.
- P5-017: completed with OSS security policy, P5 threat-model coverage, and contributor safety checklist.
- P5-018: completed with changelog, deployment dry-run, and versioned release evidence docs.
- P5-010: completed with 10-minute beta walkthrough and README onboarding links.
- P5-011: completed with P5 security review artifact and threat-model linkage without auth implementation.
- P5-012: completed with P5 final release evidence, integration verification, and full verify closure.
- P5-013: completed with `.env.example`, `Makefile`, README quickstart, and `make demo` validation.
- P5-014: completed with `CONTRIBUTING.md`, `ROADMAP.md`, and safe issue templates.
- P5-015: completed with `docs/connector-sdk.md` and executable fixture connector template.
- P5-016: completed with `docs/api.md` and safe local fixture examples.
- Auth remains explicitly deferred.

## Recommended execution order

1. P5-001 connector catalog/permission preview.
2. P5-002 secret lifecycle.
3. P5-003 incident import normalization.
4. P5-004 worker CLI/dead-letter ops.
5. P5-005 approval console.
6. P5-006 Night Autopilot policy/morning report.
7. P5-007 expanded connector/product evals.
8. P5-008 self-observability.
9. P5-009 CI-ready verification.
10. P5-010 beta onboarding/deployment docs.
11. P5-011 security/threat refresh.
12. P5-012 final release evidence.

## Team execution guidance

Use Team mode when implementing P5 because lanes can run independently after the shared contracts are defined:

- Connector/platform lane: P5-001, P5-002, P5-003, P5-007.
- Workflow/reliability lane: P5-004, P5-008, P5-009.
- Product/UI lane: P5-005, P5-006, P5-010.
- Security/QA lane: P5-011 plus adversarial tests for all tickets.
- Leader lane: integration, roadmap updates, final verify, release evidence.

Each ticket should still follow P4 discipline: plan check -> RED test -> GREEN implementation -> targeted verification -> commit -> full verification when crossing ticket group boundaries.

## P5 risks and mitigations

- Risk: accidentally drifting into auth work. Mitigation: keep auth deferred in every relevant ticket and doc; reject login/session implementation in P5.
- Risk: real connector side effects. Mitigation: fixture/dry-run by default; every write-like capability must be approval-gated and test-proven no-op.
- Risk: overclaiming paid-beta readiness. Mitigation: release docs must distinguish “paid-beta-shaped local product” from “production customer deployment”.
- Risk: UI mutation safety without auth. Mitigation: keep browser mutation forms out of scope; use API instructions/header principal until auth is reopened.
- Risk: expanded scope slows progress. Mitigation: implement in the recommended order and keep each ticket vertically testable.

## Open-source usability pivot

Updated user direction: OpsCat should be usable like an open-source project. P5 should therefore optimize for a stranger cloning the repository and getting value quickly without credentials, auth setup, or production infrastructure.

OSS-style success means:

- clone -> setup -> run demo succeeds in under 10 minutes;
- all core behavior works with fixture data and no secrets;
- contributors can understand architecture, tests, roadmap, and safety boundaries;
- connector authors can add a fixture/dry-run connector without reading the whole codebase;
- release evidence is reproducible on a laptop;
- docs avoid SaaS-only assumptions.

### P5-013 ✅ — Open-source quickstart and example environment

Goal: make first-run experience excellent for an external developer.

Plan:
1. Add `.env.example` with safe local defaults and comments.
2. Add one-command local bootstrap script or `Makefile` targets: install, test, demo, verify, run.
3. Add seed/fixture command that creates demo incidents without external credentials.
4. Update README with a “clone and run in 10 minutes” path.

Acceptance tests:
- `make demo` or equivalent command works without real secrets.
- README quickstart commands are copy-paste runnable.
- `.env.example` contains no real secrets and no production URLs.
- Verify docs explicitly say auth is deferred and local-header identity is demo-only.

Files likely touched:
- `README.md`
- `.env.example`
- `Makefile` or `scripts/bootstrap.py`
- `scripts/demo.py`
- `tests/test_oss_quickstart_docs.py`

### P5-014 ✅ — Contributor guide, roadmap, and issue templates

Goal: make the repo understandable and approachable for external contributors.

Plan:
1. Add `CONTRIBUTING.md` with local setup, test commands, coding standards, Lore commit protocol, and safety rules.
2. Add issue templates for bug, connector request, eval scenario, and safety concern.
3. Add `ROADMAP.md` summarizing P4 complete, P5 active, auth deferred, P6 candidates.
4. Add labels/ticket taxonomy in docs if GitHub labels cannot be created locally.

Acceptance tests:
- Docs tests verify contributor guide links to verify script, eval runner, connector eval runner, and safety boundary.
- Issue templates do not ask users to paste secrets/log dumps.
- Roadmap links to P5 ticket roadmap.

Files likely touched:
- `CONTRIBUTING.md`
- `ROADMAP.md`
- `.github/ISSUE_TEMPLATE/*.md`
- `tests/test_oss_contributor_docs.py`

### P5-015 ✅ — Connector SDK guide and fixture connector template

Goal: let open-source users add integrations safely.

Plan:
1. Add a connector authoring guide explaining typed capabilities, required secret names, dry-run behavior, redaction, idempotency, and eval requirements.
2. Add a fixture connector template or example module.
3. Add tests that assert template/example connectors pass registry and eval contracts.
4. Document “no broad token, no live mutation by default.”

Acceptance tests:
- Template connector exposes explicit capability metadata.
- Template connector has fixture success, missing credential, and provider failure tests.
- Connector author guide mentions connector eval requirements and no real side effects by default.

Files likely touched:
- `docs/connector-sdk.md`
- `app/connectors/example.py` or `examples/connectors/`
- `tests/test_connector_template.py`

### P5-016 ✅ — Public API and local fixture examples

Goal: make OpsCat usable as an API-first local agent product.

Plan:
1. Add generated/static API usage docs for core endpoints.
2. Add `examples/` with curl/httpie scripts for alert import, approval, reports, night autopilot, connector evals.
3. Add fixture payloads for Sentry-like, Datadog-like, Loki-like, and generic webhook events.
4. Add tests that example fixture files are valid and command docs do not contain real secrets.

Acceptance tests:
- Example fixture payloads validate against normalizer tests.
- API docs include health, mock alert, incidents, approvals, reports, operator dashboard, night autopilot, connector catalog.
- Examples use localhost and safe demo headers only.

Files likely touched:
- `docs/api.md`
- `examples/`
- `tests/test_examples.py`

### P5-017 ✅ — OSS security policy and safe disclosure docs

Goal: make public usage safer without implementing auth.

Plan:
1. Add `SECURITY.md` with supported scope, safe disclosure, secret handling, and warning not to paste production logs/secrets.
2. Add safety checklist for contributors adding actions/connectors/evals.
3. Add static tests ensuring public docs mention no raw secrets/customer data.
4. Keep auth listed as deferred and not a current production security claim.

Acceptance tests:
- `SECURITY.md` exists and states local/mock boundary.
- Contributor docs tell users not to submit secrets or customer logs.
- Tests assert docs avoid production-ready auth claims.

Files likely touched:
- `SECURITY.md`
- `docs/threat-model.md`
- `CONTRIBUTING.md`
- `tests/test_oss_security_docs.py`

### P5-018 ✅ — OSS release packaging and versioned evidence

Goal: make releases reproducible and understandable to open-source users.

Plan:
1. Add changelog/release notes structure.
2. Add versioned release evidence snapshot command.
3. Add Docker/local package instructions for running the API.
4. Add docs for what is stable vs experimental.

Acceptance tests:
- `CHANGELOG.md` includes P4 evidence and P5 planned/active sections.
- Release evidence docs include exact verify command and artifact paths.
- Docker/local run docs are linked from README.

Files likely touched:
- `CHANGELOG.md`
- `docs/release-evidence.md`
- `docs/deployment-dry-run.md`
- `tests/test_release_docs.py`

## Revised P5 priority after OSS pivot

Implement in this order for maximum open-source usability:

1. P5-013 Open-source quickstart and example environment.
2. P5-014 Contributor guide, roadmap, and issue templates.
3. P5-016 Public API and local fixture examples.
4. P5-001 Connector setup registry and permission preview.
5. P5-015 Connector SDK guide and fixture connector template.
6. P5-002 Local secret setup lifecycle and redaction audit.
7. P5-003 Incident import adapters.
8. P5-004 Durable worker CLI.
9. P5-005 Approval console without auth/session work.
10. P5-006 Night Autopilot policy editor and morning report evidence.
11. P5-007 Expanded connector/product evals.
12. P5-008 Self-observability.
13. P5-009 CI-ready verification profile.
14. P5-017 OSS security policy.
15. P5-018 OSS release packaging.
16. P5-010 Beta onboarding/deployment docs.
17. P5-011 Security/threat-model refresh.
18. P5-012 Final P5 release evidence.

## License note

Choosing an open-source license is a human/legal/product decision. P5 should add a license-selection ticket or placeholder docs, but should not unilaterally add MIT/Apache/GPL unless the project owner explicitly chooses one.
