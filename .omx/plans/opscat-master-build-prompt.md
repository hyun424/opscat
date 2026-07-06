# OpsCat Master Build Prompt

You are an autonomous senior product engineer, backend architect, and agentic-AI systems builder.

Build **OpsCat**, an AI on-call / agentic operations automation product.

## Core Product Definition
OpsCat receives incident alerts, gathers observability and deployment context, investigates likely causes, proposes or executes safe remediation according to policy, verifies recovery, and produces an auditable incident report.

OpsCat is not a generic chatbot. It is an agentic operations automation system with tools, state, policies, approvals, risk classification, and verification.

## Current Repository Context
Work inside this repository. Read all existing planning files before implementing:

- `.omx/plans/opscat-mvp-plan.md`
- `.omx/plans/opscat-product-decisions.md`
- `.omx/plans/opscat-master-build-prompt.md`

Preserve and refine these plans as implementation evolves.

## Non-Negotiable Product Principles
1. Trust before autonomy.
2. Read-only investigation can be automatic.
3. Mutation/write actions require policy checks.
4. Dangerous actions require approval or must be denied.
5. Raw logs must not be stored wholesale by default.
6. Secrets and PII must be redacted before LLM input.
7. Every recommendation must cite evidence.
8. Every action must have risk metadata and post-checks.
9. Agent must verify recovery after action.
10. Every incident must have an auditable timeline.

## MVP Goal
Implement a local MVP that demonstrates this flow:

1. Receive a mock incident alert.
2. Create an incident record.
3. Collect mock context:
   - error/log context
   - recent deploys
   - runbook
   - prior incidents
4. Generate evidence-backed hypotheses.
5. Propose a recommended action.
6. Run action through policy/risk engine.
7. If allowed, execute mock action.
8. If approval required, expose approval/rejection API.
9. Verify mock recovery.
10. Generate incident timeline and final report.

Do not start with real Sentry/GitHub/Slack integrations. Build the internal loop first with mock tools and clean interfaces.

## Recommended Stack
Use unless the repository already clearly establishes another stack:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy or SQLModel
- Pydantic
- pytest
- Docker Compose

LLM integration should be abstracted behind an interface. If no API key is configured, provide a deterministic mock agent so the MVP works offline.

## Required Architecture
Implement or plan these modules:

```text
app/
  main.py
  config.py
  db.py
  models/
    incident.py
    evidence.py
    action.py
    timeline.py
    policy.py
  schemas/
  services/
    incident_service.py
    agent_service.py
    policy_engine.py
    risk_engine.py
    report_service.py
  tools/
    base.py
    mock_alerts.py
    mock_context.py
    mock_actions.py
  agent/
    loop.py
    prompts.py
    mock_agent.py
    llm_agent.py
  api/
    health.py
    mock_alerts.py
    incidents.py
    approvals.py
  tests/
```

Adjust structure if needed, but keep boundaries clear.

## Incident State Machine
Use explicit persisted states:

- new
- queued
- investigating
- needs_more_context
- action_proposed
- waiting_approval
- executing
- verifying
- resolved
- escalated
- false_positive
- failed

Invalid state transitions should be rejected or logged.

## Agent Loop Contract
The agent must follow this order:

1. Observe incident signal.
2. Classify service, severity, environment.
3. Gather read-only context.
4. Generate hypotheses.
5. Gather evidence for/refuting hypotheses.
6. Select recommended action.
7. Run guardrail and policy check.
8. Ask for approval or execute if allowed.
9. Verify outcome.
10. Save report and memory.

The agent must not jump directly from alert to mutation.

## Agent Output Schema
Every analysis must produce structured output similar to:

```json
{
  "summary": "string",
  "affected_service": "string",
  "environment": "string",
  "severity": "low|medium|high|critical",
  "hypotheses": [
    {
      "title": "string",
      "confidence": 0.0,
      "supporting_evidence_ids": ["string"],
      "refuting_evidence_ids": ["string"],
      "status": "supported|weak|refuted|unknown"
    }
  ],
  "recommended_action": {
    "action_type": "string",
    "target": "string",
    "risk_level": "read_only|low|medium|high|prohibited",
    "requires_approval": true,
    "rationale": "string",
    "payload": {},
    "preconditions": ["string"],
    "post_checks": ["string"]
  },
  "verification_plan": ["string"],
  "escalation_condition": "string"
}
```

## Tool Registry
Start with mock tools:

- `mock.get_error_context`
- `mock.get_recent_deploys`
- `mock.get_runbook`
- `mock.search_prior_incidents`
- `mock.execute_restart_worker`
- `mock.create_incident_ticket`
- `mock.create_rollback_pr`
- `mock.verify_recovery`

Design tool interfaces so real Sentry/GitHub/Slack tools can be added later.

## Action Registry and Risk
Every action must define:

- name
- description
- base risk
- read/write/mutation trait
- reversible or not
- blast radius
- default approval requirement
- allowed environments
- required capabilities
- required preconditions
- post-checks

Policy decisions must be one of:

- ALLOW
- REQUIRE_APPROVAL
- DENY
- ESCALATE

## MVP Default Policy
Implement default policy:

Automatically allow:
- read-only mock context tools
- report generation
- timeline updates

Require approval:
- creating mock incident ticket
- creating mock rollback PR

Deny:
- production rollback
- database mutation
- arbitrary shell execution
- cloud deletion
- secret access

## Night Autopilot Requirement
Include a first version of Night Autopilot configuration, even if simulated:

- quiet hours window
- timezone
- max automatic risk
- max attempts per incident
- allowed services
- allowed environments
- wake-up/escalation conditions

For MVP, Night Autopilot can execute only mock allowlisted low-risk actions and must generate a morning report.

## APIs to Implement
Minimum APIs:

- `GET /health`
- `POST /webhooks/alerts/mock`
- `GET /incidents`
- `GET /incidents/{id}`
- `POST /incidents/{id}/investigate`
- `POST /incidents/{id}/actions/{action_id}/approve`
- `POST /incidents/{id}/actions/{action_id}/reject`
- `POST /incidents/{id}/verify`
- `GET /incidents/{id}/report`

## Mock Scenarios
Create fixtures for at least these scenarios:

1. `payment_bad_deploy`
   - payment-api errors increase after recent deploy
   - expected recommendation: rollback PR or incident ticket

2. `external_api_timeout`
   - third-party API latency/errors increase
   - expected recommendation: monitor/escalate, no unsafe mutation

3. `worker_stuck_queue_backlog`
   - worker queue grows and one worker is stuck
   - expected recommendation: restart worker if allowed

4. `false_positive_duplicate_alert`
   - duplicate alert storm with no actual customer impact
   - expected recommendation: group/dedupe, create low-priority ticket

Each scenario should define expected top hypothesis, expected evidence, expected action, and expected policy decision.

## Testing Requirements
Write tests for:

- incident creation
- state transitions
- mock tool outputs
- agent structured output validation
- policy decisions
- approval flow
- action execution
- verification flow
- report generation
- prohibited action blocking
- redaction utility

Use pytest. The MVP should run locally without external credentials.

## Developer Experience
Add:

- `README.md` with setup and demo commands
- `.env.example`
- `docker-compose.yml`
- Makefile or task commands if useful
- seed/demo script

Example demo should be:

```bash
docker compose up
curl -X POST localhost:8000/webhooks/alerts/mock \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"payment_bad_deploy"}'
```

Then user can inspect incident, approve action, verify, and view report.

## Implementation Strategy
Proceed in this order:

1. Inspect current repository.
2. Create or update docs if needed.
3. Scaffold FastAPI app.
4. Add DB models and migrations/simple table creation.
5. Implement mock scenario fixtures.
6. Implement incident service and state machine.
7. Implement tool registry.
8. Implement deterministic mock agent.
9. Implement policy/risk engine.
10. Implement approval/action flow.
11. Implement verification and report generation.
12. Add tests.
13. Run tests and fix failures.
14. Update README with demo instructions.
15. Summarize completed work and remaining risks.

## Autonomy Instructions
Work autonomously. Do not ask for permission for safe local edits, tests, scaffolding, or refactors. Ask only for destructive actions, external production credentials, or irreversible operations. Prefer small, reviewable commits/diffs. Verify before claiming completion.

## Completion Criteria
The work is complete when:

- The local app starts.
- Mock alert creates an incident.
- Agent investigation produces structured hypotheses and action proposal.
- Policy engine returns correct decision.
- Approval flow works.
- Mock action execution works.
- Verification works.
- Report generation works.
- Tests pass.
- README documents setup and demo.
