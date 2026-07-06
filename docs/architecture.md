# OpsCat MVP Architecture Notes

These notes describe the intended local MVP architecture from the build contract and the integrated worker branches inspected by worker-5 on 2026-07-06 UTC.

## Runtime boundary

OpsCat's MVP runtime is a local FastAPI API backed by SQLAlchemy persistence. SQLite is used for fast local/test fallback; Docker Compose provides the app plus PostgreSQL path. The MVP deliberately stays in mock mode: no real Sentry, GitHub, Slack, production rollback, database mutation action, or arbitrary shell execution.

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
9. `POST /night-autopilot/simulate` exercises the conservative autopilot policy path with low-risk allowlisted actions only.

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

## Safety and policy invariants

- Production-affecting actions must not execute in the MVP.
- Arbitrary shell execution must not exist as a product action.
- Read-only context tools can run automatically.
- Medium/high-risk or write-like mock actions require approval unless explicitly allowlisted by policy.
- Night Autopilot is simulated and limited to low-risk, allowlisted, non-production actions.
- Every action proposal should include rationale, evidence IDs, preconditions, post-checks, risk, and approval requirement.
- Every incident report should include status, service/environment/severity, summary, root-cause candidate, confidence, evidence, actions, execution result, and timeline.

## Current integration risk

The docs lane found API/service drift between concurrently integrated branches: code imports `execute_mock_action` and `verify_recovery` from `app.tools.mock_actions`, but the inspected integrated head's mock action module exposes a class-oriented executor instead. Tests also reference older policy API shapes. See `docs/integration-verification.md` for exact command evidence.
