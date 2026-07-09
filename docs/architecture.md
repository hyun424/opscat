# OpsCat MVP Architecture Notes

These notes describe the intended local MVP architecture from the build contract, portfolio quality bar, and integrated worker branches inspected by worker-5.

## Product architecture

OpsCat is designed as a web control plane plus a future customer-side connector:

- **Control plane:** incident state, timeline, policy decisions, approval UX, reports, and audit trail.
- **Customer-side connector:** future deployment unit that runs near observability data and executes least-privilege tool calls.
- **Local MVP:** a single FastAPI service with mock tools and local persistence that demonstrates the control loop without external side effects.

The MVP uses SQLite for fast local/test fallback and Docker Compose for the FastAPI + PostgreSQL path.

## Data boundary

OpsCat should not ingest all raw logs by default. The intended data boundary is:

1. Query only incident-relevant windows.
2. Redact secrets, tokens, PII, and customer data before any model/tool summary.
3. Store minimal evidence snippets, source references, hashes, timestamps, and action decisions.
4. Keep full raw evidence in source systems where possible.
5. Make cloud upload optional and configurable in future SaaS mode.

The current MVP uses mock evidence only and does not call real Sentry, GitHub, Slack, cloud, or shell surfaces.

## Main data flow

1. `POST /webhooks/alerts/mock` receives a Sentry-like mock alert, persists an `Incident`, enqueues a durable local `WorkflowJob`, and returns `202 Accepted`.
2. `process_next_workflow_job()` or the demo-only `?process_now=true` compatibility path starts deterministic investigation.
3. Mock context tools collect incident-relevant evidence:
   - error context,
   - recent deploys,
   - runbook guidance,
   - similar prior incidents.
4. The deterministic mock agent produces hypotheses, confidence, a recommended action, post-checks, and escalation conditions.
5. The risk/policy layer classifies the proposed action and returns `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, or `ESCALATE`.
6. If approval is required, `POST /approvals/{action_id}` records an approval or rejection.
7. Approved mock actions execute against safe local stubs only and create immutable `ActionExecutionAttempt` records.
8. Verification and report generation update the incident timeline and write a markdown incident report.
9. Connector calls use typed capabilities, redacted persistence, and idempotency replay/conflict records.
10. `GET /operator` and `GET /operator/incidents/{incident_id}` provide a server-rendered local operator dashboard.
11. `POST /night-autopilot/simulate` exercises the conservative quiet-hours automation path with low-risk allowlisted actions only.

## Module map

Expected implementation modules:

- `app/main.py` wires the FastAPI application and route modules.
- `app/api/health.py` exposes `/health`.
- `app/api/mock_alerts.py` accepts mock alert webhooks.
- `app/api/incidents.py` lists, reads, investigates, and reports incidents.
- `app/api/approvals.py` handles approval/rejection for proposed actions.
- `app/api/night_autopilot.py` exposes the simulated Night Autopilot endpoint.
- `app/api/operator.py` exposes the server-rendered local operator dashboard.
- `app/models/` contains persisted incident, evidence, action, execution attempt, workflow job, connector call record, policy, audit, identity, secret, and timeline state.
- `app/schemas/` contains API request/response contracts.
- `app/agent/` contains the deterministic mock agent loop.
- `app/tools/mock_context.py` contains read-only context-gathering stubs.
- `app/tools/mock_actions.py` contains safe local action stubs only.
- `app/services/risk_engine.py` owns action metadata and risk classification.
- `app/services/policy_engine.py` owns guardrail decisions.
- `app/services/incident_service.py` coordinates incident state transitions and actions.
- `app/services/workflow_service.py` owns the local durable incident workflow queue boundary.
- `app/services/execution_attempt_service.py` records immutable action execution attempts.
- `app/services/connector_service.py` owns typed connector execution, redaction, failure escalation, and idempotency replay.
- `app/services/report_service.py` renders markdown reports.
- `app/services/night_autopilot.py` simulates quiet-hours automation.


## Paid-beta hardening model

Before real customer use, the local MVP needs these production-facing boundaries:

- tenant/workspace ownership on every incident, evidence item, policy, action, approval, and integration;
- tenant-scoped authorization in every API/service path;
- encrypted integration token storage;
- typed connector execution instead of broad credentials;
- idempotency keys for webhooks and action execution;
- duplicate alert grouping;
- redaction before model input and report generation;
- escalation on uncertainty rather than silent failure.

These are not fully implemented in the local MVP; they are documented as paid-beta requirements in `paid-beta-readiness.md` and `threat-model.md`.

## Safety and policy invariants

- Production-affecting actions must not execute in the MVP.
- Arbitrary shell execution must not exist as a product action.
- Read-only context tools can run automatically.
- Medium/high-risk or write-like mock actions require approval unless explicitly allowlisted by policy.
- Night Autopilot is simulated and limited to low-risk, allowlisted, non-production actions.
- Every action proposal should include rationale, evidence IDs, preconditions, post-checks, risk, and approval requirement.
- Every incident report should include status, service/environment/severity, summary, root-cause candidate, confidence, evidence, actions, execution result, and timeline.
- No silent failure: unresolved, uncertain, high-risk, or unverified incidents must wake humans with evidence.

## Current integration status

The local/mock MVP now verifies through compileall, Ruff, mypy, pytest, deterministic demo smoke, coverage gate, and Docker Compose config. It remains intentionally local/mock-only: auth is header-based for demo, workflow queueing is SQLite/local rather than HA distributed infrastructure, and real provider side effects are disabled. See `docs/integration-verification.md` for command evidence.

## P93 portfolio demo architecture narrative

P93 packages the existing local/mock architecture into reviewer-readable evidence for an agentic AI incident-response/operator-replacement portfolio. The architecture story has five parts:

1. Control plane: incidents, evidence, approvals, policies, reports, and audit metadata are modeled through the FastAPI/service/data layers.
2. Tool layer: provider-shaped local/mock tools gather context, normalize signals, select runbooks, verify outcomes, and prepare reportable artifacts.
3. Reasoning loop: the operator flow is observe, correlate, investigate, decide, draft, act safely, verify, report, and improve.
4. Safety gates: readiness, policy, approval, evidence sufficiency, forbidden claims, and zero side-effect counters keep the demo local/mock-only.
5. Evidence system: P92 acceptance results, P93 portfolio pack output, release evidence, roadmap entries, and docs-profile tests make the claims reproducible.

The P93 architecture narrative is metadata only. It does not add auth work, live APIs, credentials, network, production mutation, real remediation/action execution, or external model/API calls, and it is not production autonomy.
