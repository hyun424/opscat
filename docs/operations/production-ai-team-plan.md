# OpsCat Production AI Team Plan

## Objective

Raise OpsCat from a local/mock portfolio MVP to a production-grade human-on-exception operations product using an autonomous AI development team.

The human owner provides product direction. The AI team owns planning, implementation, verification, documentation, security review, integration, and iteration.

## Current baseline

As of the latest AI team planning pass:

- FastAPI local/mock MVP exists.
- Incident state, evidence, timeline, action proposals, approvals, execution attempts, workflow jobs, connector replay records, policy decisions, escalation payloads, audit events, and reports exist.
- Dangerous production actions, shell execution, DB mutation, cloud deletion, and secret-read actions fail closed.
- Human-on-exception behavior exists for low confidence, missing context, protected domains, failed verification, and Night Autopilot max attempts.
- Workspace/tenant fields and redaction exist as paid-beta scaffolding.
- Current local verification is healthy: compileall, ruff, mypy, pytest, deterministic demo, coverage gate, and docker compose config pass locally.

This is **not production-grade yet**. It remains a single local/mock API process with local-header demo identity, no real OIDC/SSO auth, no live provider network calls, no external secret manager, no production workflow infrastructure, and no load/soak gate. However, the production foundation now includes versioned migrations, local identity and workspace membership models, service-layer tenant authorization, durable audit events, a local workflow-job boundary, immutable action execution attempts, connector idempotency replay records, a typed connector/capability boundary, a local encrypted secret-store abstraction, Sentry-style read-only recorded fixtures, dry-run Slack wake-up previews, dry-run GitHub issue drafts, connector failure escalation evidence, and a server-rendered operator dashboard MVP.

## Non-negotiable product promise

OpsCat must reduce continuous human monitoring by handling routine incidents end-to-end and waking humans only when safety, confidence, context, authority, or verification requires it.

## AI team topology

### 1. Lead Orchestrator
- Owns roadmap, quality bar, integration, release decisions, and final verification evidence.
- Maintains the single source of truth in docs, tests, plans, and commit history.
- Never claims production readiness without green release gates.

### 2. Planning Agent
- Produces PRDs, milestones, acceptance criteria, task graphs, and replans when evidence changes.
- Converts vague ambition into testable implementation tickets.

### 3. Architect Agent
- Owns production architecture decisions: ingestion, correlation, workflows, connectors, policy/action sandbox, auth, tenancy, secrets, persistence, deployment.
- Rejects shortcuts that would block production hardening.

### 4. Backend/Platform Agent
- Implements APIs, persistence, migrations, background jobs, service catalog, runbook index, connector framework, policy engine, action executor, verification engine.

### 5. Frontend/Product Agent
- Builds operator product surface: incident inbox, reasoning timeline, approval console, policy editor, Night Autopilot settings, connector setup, morning reports.

### 6. Security Agent
- Owns threat model, authz, tenant isolation, encrypted secrets, least privilege, redaction, dangerous-action policy, and audit logs.

### 7. QA/Eval Agent
- Owns tests, golden evals, no-silent-failure invariants, connector failure tests, e2e/browser tests, load/soak tests, release evidence.

### 8. Docs/Portfolio Agent
- Keeps README, onboarding, architecture docs, production gaps, demo scripts, and portfolio narrative truthful and impressive.

## Operating loop

Every autonomous AI development cycle follows:

1. Update plan/task graph.
2. Implement one vertical slice.
3. Add/adjust regression tests before or with behavior changes.
4. Verify with lint, typecheck, tests, demo/smoke, and relevant security checks.
5. Security-review changed trust boundaries.
6. Document behavior and known gaps.
7. Commit with Lore protocol.
8. Re-evaluate roadmap and select next highest-leverage slice.

## Autonomy policy

AI may autonomously:

- edit local code, docs, tests, scripts, and mock fixtures;
- create local connector abstractions and fake provider fixtures;
- run local tests/builds/lint/typecheck;
- create synthetic incidents/logs/evals;
- refactor for quality;
- create local Docker/dev scripts.

AI must not autonomously:

- mutate real production systems;
- spend money on cloud resources;
- use real customer data;
- commit real secrets;
- enable real destructive actions;
- use broad provider tokens or credentials without explicit human authority.

## Target production architecture

Production OpsCat should evolve from a synchronous local process into:

1. **Control plane**
   - incidents, policies, approvals, audit, reports, workflow orchestration, UI.

2. **Durable workflow workers**
   - ingestion normalization, correlation, investigation, action execution, verification, notification, dead-letter handling.

3. **Customer-side connector agent**
   - runs near customer systems, owns raw data access and real credentials, returns sanitized evidence/results.

4. **Strict action sandbox**
   - typed action registry, capability grants, dry-run previews, preconditions, approvals, immutable attempts, post-checks.

5. **Production trust layer**
   - authn/authz, tenant isolation, encrypted secret store, migrations, audit logs, rate limits, retries, observability.

## Production architecture decisions

### Ingestion boundary

Webhook receivers should only authenticate, normalize, redact, persist, enqueue, and return `202`. They should not run full investigation synchronously.

Required entities:

- `SignalEnvelope`
- `NormalizedSignal`
- `WebhookDelivery`
- `IncidentSignal`
- idempotency keys per tenant/source/event

### Correlation layer

Introduce correlation between signals and incidents using:

- source fingerprint;
- service/environment;
- deploy window;
- topology/service catalog;
- ownership/runbook mapping;
- duplicate/suppression rules;
- severity and blast radius.

### Durable incident workflow

Replace one-shot request-path investigation with durable workflow steps:

1. Ingest signal.
2. Correlate/update incident.
3. Gather read-only context.
4. Redact and persist evidence.
5. Generate hypotheses with evidence IDs.
6. Score confidence and evidence sufficiency.
7. Propose action plan.
8. Evaluate deterministic policy.
9. Wait for approval or escalate.
10. Execute sandboxed action.
11. Verify recovery.
12. Generate report and metrics.

### Connector contract

Every connector must expose:

- typed capabilities;
- input/output schemas;
- tenant/workspace binding;
- redaction boundary;
- idempotency key;
- dry-run support where relevant;
- timeout/retry policy;
- post-check verifier;
- audit event emission.

Initial real connector scope should be limited to:

- Sentry/Datadog-style read-only incident context;
- Slack wake-up messages;
- GitHub issue/PR draft creation after approval.

No production rollback, arbitrary shell, cloud deletion, DB mutation, or secret-read action should exist by default.

### Auth, tenancy, and secrets

Workspace headers/body fields are local-demo scaffolding only. Production requires:

- authenticated human identity;
- service-account identity for connectors;
- workspace membership/roles from verified claims;
- RBAC/ABAC for incident read, approval, policy edit, connector install, action execution;
- service-layer tenant guards, not only route filters;
- encrypted secret storage or external secret provider;
- secret rotation/delete path;
- no raw secrets in LLM context, reports, logs, audit, or API responses.

### Queues and persistence

Add durable boundaries before real connectors:

- `ingest.normalization`
- `correlation`
- `incident.workflow`
- `context.gather`
- `action.execute`
- `verification`
- `notifications`
- dead-letter queues

Persistence upgrades:

- Alembic or equivalent migrations;
- immutable audit log;
- action execution attempt table;
- report artifacts in object/object-like storage;
- unique constraints for webhook/action idempotency;
- retention policy for raw payloads/evidence.

## Milestones

### M0 — Green local MVP baseline
Status: complete enough for current planning.

Release gate:

- compileall passes;
- ruff passes;
- mypy passes;
- pytest passes;
- demo/smoke passes;
- docker compose config passes;
- tracked generated artifact scan is clean.

### M1 — Production control-plane foundation
Target: first production-hardening slice.

Scope:

- release-gate script;
- DB migration framework;
- real local auth identity model;
- workspace membership/roles;
- service-layer tenant authorization;
- durable audit log.

Status: completed for the local/mock foundation; production OIDC/SSO remains a later paid-beta gate.

Acceptance:

- cross-workspace API and service-layer access fails;
- `X-OpsCat-Workspace` is demo-only, not trusted production auth;
- approvals require actor authority;
- audit events exist for proposal, policy decision, approval/rejection, execution, verification, escalation, connector call, and report generation.

### M2 — Connector-ready platform

Scope:

- connector interface and capability registry;
- encrypted secret abstraction;
- fake connector contract tests;
- Sentry/Datadog-style read-only adapter;
- Slack wake-up adapter;
- GitHub draft issue/PR adapter;
- connector timeout/failure escalation.

Acceptance:

- connector methods are typed;
- missing credentials fail closed;
- connector failures create timeline/audit evidence;
- no connector can execute arbitrary shell;
- no real mutation occurs without policy + approval.

Status: completed for local/mock connector readiness. The platform now has a typed connector registry, local encrypted secret abstraction, fake observability connector, Sentry-style read-only recorded-fixture connector, Slack dry-run wake-up preview adapter, GitHub dry-run draft issue adapter, fail-closed missing credential handling, and connector timeout/failure escalation into evidence, timeline, audit, and human escalation. Real provider network calls and real external mutations remain explicitly out of scope until paid-beta hardening.

### M3 — Operator product surface

Scope:

- web dashboard;
- incident inbox;
- incident detail and evidence timeline;
- approval console;
- policy editor;
- runbook/service catalog UI;
- Night Autopilot settings;
- connector setup/status;
- browser smoke tests.

Acceptance:

- non-developer can operate alert → incident → approval/reject → report flow;
- UI shows evidence IDs, confidence, policy decision, preconditions, post-checks, payload preview;
- UI respects workspace scoping.

### M4 — Agent reliability and eval system

Scope:

- expand golden evals to 20, then 50+;
- confidence/evidence scoring;
- runbook matching;
- duplicate/related alert grouping;
- post-action verification workflows;
- adversarial prompt/log injection evals;
- no-silent-failure invariant suite;
- eval report per release.

Acceptance:

- low confidence escalates;
- missing context escalates;
- protected domains escalate/deny;
- failed verification escalates;
- duplicate alerts group;
- adversarial text cannot override deterministic policy.

### M5 — Limited real paid-beta candidate

Scope:

- background workers;
- rate limits/retries;
- OpsCat self-observability;
- deployment manifests;
- backups/restore;
- Slack real wakeups;
- GitHub draft actions;
- Sentry read-only ingestion;
- security review report;
- onboarding checklist.

Acceptance:

- real integrations are low-risk only;
- no unsupported production mutation exists;
- background jobs are retry-safe and idempotent;
- deployment guide includes secrets, migrations, backups, rollback;
- security review signs off on auth, tenancy, secrets, connectors, audit, redaction, and policy.

## First implementation tickets

### P0-001 — Release-gate script
Create `scripts/verify.sh` or equivalent that runs compileall, ruff, mypy, pytest, demo, docker compose config, diff check, and tracked artifact scan.

### P0-002 — No-silent-failure invariant suite
Add parametrized tests over resolved/escalated/denied/executed paths ensuring terminal state always has evidence, timeline, report/escalation, redaction, and correct action status.

### P0-003 — Coverage gate
Add coverage tooling and initial realistic threshold, then ratchet for safety-critical modules.

### P1-004 — Migration framework
Add initial migrations for current schema and remove production reliance on `create_all`.

### P1-005 — Auth identity and membership model
Introduce users/service accounts/workspace memberships/roles, keeping demo header mode explicitly separate.

### P1-006 — Service-layer tenant authorization
Centralize incident/action/report/approval access checks and test bypass attempts.

### P1-007 — Durable audit log
Add append-only audit events for all policy/action/approval/connector/report transitions.

### P1-008 — Connector interface and capability registry
Define connector contracts, capability grants, fake connector, and policy integration.

### P1-009 — Secret storage abstraction
Status: complete for local/mock foundation. Added scoped encrypted secret records, a local envelope provider, audit events, redaction, role checks, and fail-closed tests. Future production work must replace the local provider with external KMS/secret-manager integration before real customer credentials.

### P1-010 — Sentry-style read-only connector slice
Status: complete for local/mock foundation. Implemented a Sentry-shaped read-only connector backed by recorded sanitized fixtures, scoped secret lookup, missing-credential fail-closed behavior, redaction assertions, and registry capability tests.

### P1-011 — Connector timeout/failure escalation
Status: complete for local/mock foundation. Provider timeout, malformed result, failed result, read-only contract violation, and missing credential paths fail closed and create audit/timeline/evidence/escalation records when incident context is available.

### P1-012 — Slack wake-up adapter
Status: complete for dry-run-only local/mock foundation. Slack wake-up builds redacted previews and records audit evidence; real sends are blocked by the service boundary and by the connector itself.

### P1-013 — GitHub draft issue adapter
Status: complete for dry-run-only local/mock foundation. GitHub draft issue previews are approval-gated, redacted, audited, and never create live issues in the MVP even if a caller attempts a real send.

## Updated remaining execution order

1. **P2-014 Durable workflow queue boundary** — status: complete for local/mock MVP. Webhooks enqueue by default, `process_now=true` preserves the synchronous demo path, and workflow start/completion evidence is audited. Production still needs distributed workers, lease recovery, metrics, and dead-letter operations.
2. **P2-015 Action execution attempt model** — status: complete for persisted mock actions. Attempts capture preconditions, execution result, post-check result, retry eligibility, and failure classes. Production still needs richer retry orchestration and executor isolation.
3. **P2-016 Connector failure/idempotency matrix expansion** — status: complete for local/mock foundation. Same-key/same-hash replays, same-key/different-hash fails closed, failed calls do not duplicate escalation side effects, and results are redacted before persistence.
4. **P3-017 Operator dashboard MVP** — status: complete for server-rendered local dashboard. Inbox/detail are workspace-scoped and read-only for browser mutations. Production still needs sessions, CSRF, polish, connector setup, and policy editor surfaces.
5. **P4-018 Eval expansion** — status: first slice complete. Golden eval corpus is 20+ scenarios with a deterministic local runner and JSON/Markdown reports in the release gate. Next: grow to 50+ scenarios, add connector-failure evals, and add browser E2E evidence.
6. **P5-019 Paid-beta deployment hardening** — CI, deployment manifests, backup/restore, OTel/self-monitoring, security review.

## Production release gates

OpsCat is not production-grade until all are true:

1. Green local/CI-equivalent gate.
2. Authn/authz implemented and tested.
3. Tenant/workspace isolation enforced in API and service layer.
4. Secrets encrypted or delegated to secret manager.
5. Connector credentials scoped and audited.
6. No arbitrary shell execution path.
7. No default production destructive actions.
8. Every action has policy decision, preconditions, approval if needed, immutable audit, execution attempt, post-check.
9. Failed execution/verification escalates.
10. Low confidence/missing context/protected domain escalates.
11. Webhooks/actions are idempotent and retry-safe.
12. 50+ evals cover common, ambiguous, protected, duplicate, connector-failure, and adversarial scenarios.
13. Operator UI supports core flow.
14. Deployment, migration, backup/restore, observability, and rollback docs exist.
15. Docs truthfully state remaining unsupported actions.

## Immediate execution recommendation

Start with a controlled M1 foundation team:

- Planning Agent: maintain milestone/task graph and update this doc after every cycle.
- Backend Agent: release-gate script + migrations.
- Security Agent: auth identity/membership and service-layer tenant guards.
- QA Agent: no-silent-failure invariants + coverage gate.
- Architect Agent: connector contract ADR.

Do not start real connector credentials or real actions until M1 gates are green.
