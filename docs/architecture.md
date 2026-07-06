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

1. `POST /webhooks/alerts/mock` receives a Sentry-like mock alert.
2. The incident service persists an `Incident` and starts deterministic investigation.
3. Mock context tools collect incident-relevant evidence:
   - error context,
   - recent deploys,
   - runbook guidance,
   - similar prior incidents.
4. The deterministic mock agent produces hypotheses, confidence, a recommended action, post-checks, and escalation conditions.
5. The risk/policy layer classifies the proposed action and returns `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, or `ESCALATE`.
6. If approval is required, `POST /approvals/{action_id}` records an approval or rejection.
7. Approved mock actions execute against safe local stubs only.
8. Verification and report generation update the incident timeline and write a markdown incident report.
9. `POST /night-autopilot/simulate` exercises the conservative quiet-hours automation path with low-risk allowlisted actions only.

## Module map

Expected implementation modules:

- `app/main.py` wires the FastAPI application and route modules.
- `app/api/health.py` exposes `/health`.
- `app/api/mock_alerts.py` accepts mock alert webhooks.
- `app/api/incidents.py` lists, reads, investigates, and reports incidents.
- `app/api/approvals.py` handles approval/rejection for proposed actions.
- `app/api/night_autopilot.py` exposes the simulated Night Autopilot endpoint.
- `app/models/` contains persisted incident, evidence, action, policy, and timeline state.
- `app/schemas/` contains API request/response contracts.
- `app/agent/` contains the deterministic mock agent loop.
- `app/tools/mock_context.py` contains read-only context-gathering stubs.
- `app/tools/mock_actions.py` contains safe local action stubs only.
- `app/services/risk_engine.py` owns action metadata and risk classification.
- `app/services/policy_engine.py` owns guardrail decisions.
- `app/services/incident_service.py` coordinates incident state transitions and actions.
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

## Current integration risk

The latest inspected leader head (`055ac28158b98cd757861041548ed35bfaac3073`) fails before app import because `app/models/action.py` contains an indentation syntax error in the SQLAlchemy relationship block. Until that is fixed, the API, demo, and tests cannot prove the intended flow. See `docs/integration-verification.md` for exact command evidence.
