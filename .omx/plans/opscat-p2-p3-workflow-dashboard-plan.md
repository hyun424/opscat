# OpsCat P2/P3 Workflow Queue + Operator Dashboard Plan

Generated: 2026-07-07
Mode: read-only planning handoff. No code implementation performed.
Sequence: planning -> plan review -> implementation -> verification.

## Evidence-grounded scope

Current inspected baseline:

- `app/api/mock_alerts.py` currently returns `201` and calls `create_and_investigate(...)` inline, so ingestion is synchronous.
- `app/services/incident_service.py` currently creates incidents, runs `AgentLoop().investigate(...)`, approves/rejects, executes mock actions, verifies recovery, escalates, and saves reports in request-path service functions.
- `app/models/action.py` has `ActionProposal.execution_result` but no immutable execution-attempt table.
- `app/services/connector_service.py` has typed connector calls, audit events, redacted failure escalation, and request idempotency keys on the request dataclass, but no durable connector call replay table.
- `app/schemas/incidents.py` exposes incident/evidence/action/timeline data; action attempts and dashboard-specific views are absent.
- `app/main.py` mounts API routers only; no `/operator` dashboard router exists.
- `app/migrations/runner.py` applies fixed migration modules through `0004_secret_records`; new tables require adding `0005...` and updating tests.
- `tests/conftest.py` required endpoint list does not include workflow or operator routes yet.

## Recommended design decision

Use local SQL-backed durability, not new infrastructure: add workflow/job, action-attempt, and connector-call-record tables plus service boundaries, then expose a minimal FastAPI server-rendered operator dashboard. This keeps the M2 local/mock safety model intact while creating production-shaped seams for a future queue worker and real UI.

Rejected for this phase: Redis/Celery/RQ, a JS SPA, and live connector mutations. They increase dependency and safety risk before the durable boundaries are proven.

## Sequence plan

### 1. Planning gate: freeze behavior contracts before edits

Deliverables:

- Confirm ticket order stays `P2-014 -> P2-015 -> P2-016 -> P3-017` because later UI depends on durable backend state.
- Define compatibility policy for `POST /webhooks/alerts/mock`: preferred default `202 Accepted` with queued incident; optional `process_now=true` escape hatch for demo/tests if preserving existing flow is necessary.
- Decide that all new persistence writes must be tenant/workspace scoped and redacted before API/dashboard exposure.

Acceptance criteria:

- Plan reviewer can point each ticket to specific tests and files below.
- No live external calls or production mutations are introduced.

### 2. Plan review gate: write failing tests first

Add/adjust tests before implementation:

- `tests/test_workflow_queue.py`
  - mock alert creates incident + pending workflow job and returns queued state without immediate investigation;
  - local worker processes pending job and records job lifecycle timeline/audit;
  - duplicate idempotency key reuses the incident and does not create duplicate active jobs.
- `tests/test_action_execution_attempts.py`
  - approving an action creates an immutable attempt with precondition, execution, post-check, status, retry eligibility, and idempotency fields;
  - execution failure/post-check failure escalates with attempt metadata and redaction.
- Extend `tests/test_connector_contract.py`
  - connector idempotency replay returns prior redacted result;
  - replay does not duplicate evidence, timeline, audit, or human-escalation side effects;
  - stale/rate-limited/malformed/failure outputs remain fail-closed and redacted.
- `tests/test_operator_dashboard.py`
  - `/operator` inbox and `/operator/incidents/{id}` render workspace-scoped incident details;
  - detail view shows evidence, timeline, actions, approvals/rejections, attempts, audit/connector status signals;
  - cross-workspace incident detail is hidden or 404/403.
- Update `tests/test_api_contract.py` / `tests/conftest.py` for expected new routes/status only after the behavior contract is explicit.

Acceptance criteria:

- Targeted tests fail for missing behavior, not import/syntax errors.
- Reviewer signs off that tests cover queue boundary, attempt model, connector idempotency, dashboard scoping, and redaction.

### 3. Implementation phase A: P2-014 durable workflow queue boundary

Primary touchpoints:

- `app/models/workflow.py`: add `WorkflowJob` with tenant/workspace, incident id, queue/type, status (`pending`, `leased`, `succeeded`, `failed`, `dead_lettered`), dedupe key, payload, attempts, lease owner/expiry, last error, timestamps.
- `app/migrations/versions/0005_workflow_jobs_action_attempts.py`: create new workflow table(s); update `app/migrations/runner.py` and `tests/test_migrations.py`.
- `app/models/__init__.py`: export/load new persistence model(s).
- `app/services/workflow_service.py`: enqueue, dedupe, claim, process, mark success/failure/dead-letter.
- `app/services/incident_service.py`: split `create_mock_incident`, enqueue, and investigation processing; keep explicit compatibility helper only if needed.
- `app/api/mock_alerts.py`: return queued response (`202` preferred) and enqueue job.

Acceptance criteria:

- Ingestion can complete while incident remains `queued`.
- Worker processing advances the incident through existing investigation/policy states using existing `AgentLoop` and state machine.
- Duplicate alerts/idempotency keys do not create duplicate incidents or duplicate active jobs.
- Job lifecycle has audit/timeline evidence.

### 4. Implementation phase B: P2-015 action execution attempt model

Primary touchpoints:

- `app/models/action.py`: add `ActionExecutionAttempt` relationship/table fields for tenant/workspace/action/incident, attempt number, idempotency key, status, preconditions, execution result, post-check result, retry eligibility, failure class, redacted error, timestamps.
- `app/services/execution_attempt_service.py`: create/start/succeed/fail attempt helpers with centralized redaction.
- `app/services/incident_service.py` and `app/services/night_autopilot.py`: wrap mock action execution and verification in attempt lifecycle.
- `app/schemas/incidents.py`: expose attempts under `ActionRead` for API/dashboard consumption.
- `app/services/escalation.py` and `app/services/report_service.py`: include attempt metadata in escalation/report output without leaking secrets.

Acceptance criteria:

- Every approved execution path creates one immutable attempt record.
- Failed execution and failed post-check carry retry eligibility and escalation context.
- Existing no-silent-failure and report invariants still pass.

### 5. Implementation phase C: P2-016 connector failure/idempotency expansion

Primary touchpoints:

- `app/models/connector.py` or `app/models/workflow.py`: add `ConnectorCallRecord` with scoped idempotency key, connector/capability, request hash, status, redacted result, side-effect marker, timestamps.
- `app/services/connector_service.py`: replay completed matching calls before provider execution; persist redacted completed/failed records; ensure failure escalation is emitted once per idempotent call.
- `app/connectors/base.py`: keep request/result dataclasses stable unless a small `retry_after`/failure-class field is needed.
- `app/services/escalation.py`: ensure new connector failure classes map to deterministic human guidance.
- `tests/test_connector_contract.py`: expand timeout, missing credential, malformed, contract violation, rate-limit, stale idempotency, replay, and redaction cases.

Acceptance criteria:

- Same tenant/workspace/connector/capability/idempotency key replays prior result and does not duplicate side effects.
- Different scope or materially different request hash is not incorrectly replayed.
- Connector failures remain fail-closed and redacted across audit/timeline/evidence/API.

### 6. Implementation phase D: P3-017 operator dashboard MVP

Primary touchpoints:

- `app/api/operator.py`: add server-rendered HTML routes:
  - `GET /operator` incident inbox;
  - `GET /operator/incidents/{incident_id}` detail;
  - optional POST forms for approve/reject that call existing service layer or link to existing endpoints.
- `app/services/operator_view_service.py` if route queries become nontrivial.
- `app/main.py`: mount operator router.
- `app/schemas/incidents.py` / view helpers: reuse API models where possible.
- `tests/test_operator_dashboard.py`: HTML smoke tests and workspace scoping.
- Docs: `README.md`, `docs/demo-walkthrough.md`, and `docs/operations/production-ai-team-plan.md` for queued workflow and dashboard usage.

Acceptance criteria:

- Inbox lists only current principal's workspace incidents with status/severity/service/time.
- Detail page shows summary, evidence, timeline, action policy, approval/reject affordance, execution attempts, report link, and connector/audit status.
- Dashboard remains basic server-rendered HTML; no frontend dependency added.

## Risks and mitigations

- Webhook behavior change may break existing tests/demo: add explicit contract update and, if needed, `process_now=true` compatibility for demos only.
- Queue table may be mistaken for production distributed queue: document it as a local durable boundary, not HA infrastructure.
- Attempt/connector persistence can leak secrets: enforce `redact_value` before persistence/exposure and test with tokens/emails.
- Idempotency can suppress valid retries: scope keys by tenant/workspace/connector/capability and compare request hash; model retry separately from replay.
- Dashboard scope can accidentally bypass authorization: use existing `Principal` dependencies and service-layer same-scope checks; test cross-workspace invisibility.

## Verification gates

1. RED gate: new targeted tests fail for expected missing behavior only.
2. Phase gates: run each targeted suite after its implementation phase:
   - `uv run --no-sync --extra dev pytest tests/test_workflow_queue.py -q`
   - `uv run --no-sync --extra dev pytest tests/test_action_execution_attempts.py -q`
   - `uv run --no-sync --extra dev pytest tests/test_connector_contract.py -q`
   - `uv run --no-sync --extra dev pytest tests/test_operator_dashboard.py -q`
3. Regression gate: `uv run --no-sync --extra dev pytest -q`.
4. Static gate: `python3 -m compileall -q app tests scripts`, `uv run --no-sync --extra dev ruff check app tests scripts`, `uv run --no-sync --extra dev mypy app tests scripts`.
5. Release gate: `bash scripts/verify.sh` green.
6. Manual/readout gate: dashboard HTML smoke evidence and updated docs identify remaining non-production gaps.

## Handoff guidance

- Recommended execution mode: `$ultragoal` or `$team` because the backend durability, connector matrix, and dashboard can be parallelized after shared models/migrations are agreed.
- Suggested staffing: planner/reviewer for test contract review, executor for backend phases A-C, executor/designer for dashboard HTML, verifier for final gate.
- Stop condition: all acceptance criteria above pass, `scripts/verify.sh` is green, and docs explicitly state the queue/dashboard are local/mock MVP surfaces.


## Plan Review Changelog

- Planner review agreed with the P2/P3 sequence and emphasized RED tests before implementation plus final `bash scripts/verify.sh`.
- Architect review approved the SQL-backed local/mock boundary approach and rejected adding Redis/Celery/SPA dependencies at this stage.
- Applied architect must-fix items: split migrations by boundary (`0005`, `0006`, `0007`), make `process_now=true` explicit compatibility, and include stale docs cleanup before final handoff.
- Implementation guardrail: build attempts around persisted `ActionProposal`, not the in-memory demo `ActionService` path.
