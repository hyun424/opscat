# OpsCat MVP Plan

## 1. Product Thesis
OpsCat is an AI on-call agent that receives incident alerts, gathers observability and deployment context, investigates likely causes, proposes safe remediation, requests human approval for risky actions, and verifies recovery.

## 2. Target User
Small to mid-sized engineering teams that use Sentry, GitHub, and Slack but do not have dedicated 24/7 SRE/on-call triage capacity.

## 3. MVP Scope

### In scope
- Receive alert webhook from Sentry or mock alert source.
- Fetch related error context from Sentry.
- Fetch recent commits/releases/deployments from GitHub.
- Match alert to service/runbook.
- Generate incident summary, hypotheses, evidence, and recommended next actions.
- Send Slack incident message with action buttons.
- Support approval-gated actions:
  - create GitHub issue
  - create rollback/remediation PR draft
  - generate incident report markdown
- Verify recovery using mocked or real Sentry issue status / metric trend.

### Out of scope for MVP
- Direct production rollback.
- Kubernetes mutation actions.
- Cloud resource deletion/modification.
- Full Datadog/Grafana/Loki integration.
- Fully autonomous remediation without approval.

## 4. Core Agent Loop
1. Observe: receive alert.
2. Contextualize: collect Sentry, GitHub, runbook, and prior incident context.
3. Hypothesize: generate likely causes.
4. Investigate: call tools to validate/refute hypotheses.
5. Decide: choose recommended response.
6. Guardrail: classify action risk and require approval where needed.
7. Act: create issue/PR/report after approval.
8. Verify: check whether error frequency/status improved.
9. Remember: store incident timeline and outcome.

## 5. Recommended Tech Stack
- Backend: Python FastAPI
- Agent orchestration: OpenAI Agents SDK or LangGraph
- DB: PostgreSQL
- Queue/background jobs: Redis + RQ/Celery, or simple asyncio first
- Integrations:
  - Sentry API/webhook
  - GitHub API
  - Slack API
- Local dev: Docker Compose
- Optional frontend later: Next.js dashboard

## 6. Data Model

### Incident
- id
- source
- status: new | investigating | waiting_approval | action_taken | verifying | resolved | escalated
- service
- environment
- severity
- started_at
- alert_payload
- summary
- root_cause_candidate
- confidence
- created_at / updated_at

### Evidence
- id
- incident_id
- type: sentry_issue | log | metric | deploy | commit | runbook | user_feedback
- source_url
- content
- collected_at

### ActionProposal
- id
- incident_id
- action_type
- risk_level: low | medium | high
- requires_approval
- rationale
- proposed_payload
- status: proposed | approved | rejected | executed | failed

### IncidentTimelineEvent
- id
- incident_id
- timestamp
- actor: system | agent | human | integration
- event_type
- content

## 7. Milestones

### Milestone 0: Repo scaffold
Deliverables:
- FastAPI app
- Docker Compose for app + Postgres
- basic env/config layout
- health check endpoint

Acceptance criteria:
- `docker compose up` starts app and DB.
- `/health` returns OK.

### Milestone 1: Mock incident engine
Deliverables:
- mock alert webhook
- sample Sentry-like error payloads
- mock GitHub deploy history
- runbook YAML files
- incident state persisted in DB

Acceptance criteria:
- POST `/webhooks/alerts/mock` creates incident.
- Agent can produce summary and hypotheses from mock data.

### Milestone 2: Agent investigation loop
Deliverables:
- tool interface
- tools: get_error_context, get_recent_deploys, get_runbook, search_prior_incidents
- hypothesis/evidence/action response schema
- deterministic state transitions

Acceptance criteria:
- Agent must cite at least 2 evidence items for every top recommendation.
- Agent must mark unsupported hypotheses as low confidence.

### Milestone 3: Slack approval flow
Deliverables:
- Slack incident summary message
- approve/reject/more-investigation buttons
- approval state stored in DB

Acceptance criteria:
- Slack message includes severity, affected service, evidence, recommendation, and buttons.
- Approved action transitions from proposed to approved.

### Milestone 4: GitHub actions
Deliverables:
- create GitHub issue action
- create remediation/rollback PR draft action
- incident report markdown generator

Acceptance criteria:
- Approved action creates GitHub issue/PR in test repo.
- Generated issue/PR contains incident evidence and recommended verification.

### Milestone 5: Real Sentry integration
Deliverables:
- Sentry webhook parser
- Sentry issue/event fetcher
- Sentry project/service mapping

Acceptance criteria:
- Real Sentry test alert creates an incident.
- Agent includes stack trace/error fingerprint in analysis.

### Milestone 6: Verification and demo polish
Deliverables:
- post-action verification job
- final incident report
- demo scenario scripts
- README and architecture diagram

Acceptance criteria:
- A full demo runs from alert to Slack approval to GitHub issue/PR to report.
- Every incident has an auditable timeline.

## 8. Guardrails
- No high-risk action executes without explicit approval.
- Production mutation tools are disabled in MVP.
- Every recommendation must include evidence links or evidence records.
- Every action must define post-checks before execution.
- Secrets are never passed to the LLM.
- Raw logs are truncated and redacted before model input.

## 9. Evaluation Plan

### Unit tests
- webhook parsing
- incident state transitions
- risk classification
- runbook matching
- action schema validation

### Integration tests
- mock alert to incident creation
- incident to agent proposal
- Slack interaction callback handling
- GitHub issue/PR creation with mocked API

### End-to-end demo test
- simulate payment-api error spike
- find recent bad deploy
- propose rollback PR
- approve in Slack
- create GitHub PR
- generate report

### Quality metrics
- Time to first summary < 60 seconds for mock scenario.
- 100% of proposed actions have risk level and post-check.
- 0 high-risk actions executable without approval.
- 90%+ test incidents produce correct top-1 or top-2 cause in curated eval set.

## 10. First Build Order
1. Create repo scaffold.
2. Define incident schema and state machine.
3. Add mock alert + mock context tools.
4. Build agent output schema.
5. Add Slack summary later, after terminal demo works.
6. Add GitHub action after approval flow works.
7. Add Sentry last, once internal flow is stable.

## 11. Architecture Decision: Web Control Plane + Customer-Side Agent

### Decision
OpsCat should not be desktop-first. The recommended architecture is a web control plane plus a customer-side OpsCat Agent/Connector that runs near the customer's observability data.

### Rationale
Incident response is a team workflow that needs webhooks, Slack approvals, GitHub actions, audit trails, multi-user access, and 24/7 availability. A desktop app is poor as the primary runtime because it depends on one user's machine being online and has weaker fit for server-side integrations.

### Data Boundary
Raw logs should not be copied wholesale into OpsCat Cloud by default. The customer-side agent should query Sentry/Loki/CloudWatch/etc. on demand, redact sensitive fields, summarize or extract small evidence windows, then send only metadata, evidence snippets, references, and action proposals to the control plane.

### Deployment Modes
1. Local/dev mode: Docker Compose, mock data, local web UI/API.
2. SaaS mode: OpsCat Cloud web app + customer-side connector in the user's infra.
3. Enterprise/private mode: fully self-hosted OpsCat in the customer's VPC/Kubernetes cluster.

### Desktop Role
A desktop app is optional later as a local notifier or developer convenience tool, but it should not be the primary product surface.

## 12. Permission Model: Least-Privilege Capability Grants

### Decision
OpsCat must support explicit, granular permission selection. Customers should decide which systems OpsCat can read, which actions it can propose, and which actions it can execute after approval.

### Permission Tiers
1. Observe-only
   - Receive alerts
   - Read logs/errors/metrics/deploy metadata
   - Generate summaries and hypotheses
   - No external writes

2. Recommend
   - Everything in observe-only
   - Propose runbook steps and remediation plans
   - Draft Slack messages
   - No execution

3. Approval-gated execute
   - Everything in recommend
   - Execute selected low/medium-risk tools only after human approval
   - Examples: create GitHub issue, create rollback PR, toggle approved feature flag

4. Autonomous low-risk execute
   - Execute explicitly allowlisted reversible actions without approval
   - Examples: create ticket, silence duplicate alert, restart non-prod worker
   - Must include post-checks and audit logs

5. High-risk restricted
   - Production rollback, database mutations, cloud resource deletion, security policy changes
   - Disabled by default
   - Requires admin approval, break-glass workflow, and extra audit evidence

### Capability Grants
Permissions should be represented as capability grants, not broad roles.

Examples:
- sentry:issues:read
- sentry:events:read
- github:repos:read
- github:issues:write
- github:pull_requests:write
- slack:messages:write
- slack:interactions:read
- loki:logs:read
- kubernetes:pods:read
- kubernetes:deployments:restart:staging
- feature_flags:toggle:approved_flags_only

### Execution Policy
Every tool call must be checked against:
- tenant policy
- environment policy
- service policy
- action risk level
- approval requirement
- requester identity
- current incident state

### UI Requirement
The web UI must provide a permissions screen where admins can enable/disable each integration and action. Each permission should show:
- what data can be read
- what changes can be made
- whether approval is required
- risk level
- audit trail location

### Default MVP Policy
Start with:
- read Sentry issue/event context
- read GitHub commits/releases
- write Slack messages
- write GitHub issues only after approval
- create PR drafts only after approval
- no production infrastructure mutation

## 13. Interaction Model: Codex-Style Tool Approval Modes

### Decision
OpsCat should expose Codex-style execution controls. Users can review each proposed tool call interactively, approve with one click/enter, or configure auto-approval policies for trusted low-risk actions.

### Execution Modes
1. Manual Approval Mode
   - Every write/mutation tool call pauses for user approval.
   - UI shows command/action, target, risk, rationale, evidence, expected effect, and rollback/post-check.

2. Smart Approval Mode
   - Read-only tools execute automatically.
   - Low-risk write actions execute automatically if allowlisted.
   - Medium/high-risk actions require approval.

3. Autopilot Mode
   - Allowlisted low-risk actions execute automatically.
   - Medium-risk actions may execute automatically only if explicit service/environment policy allows it.
   - High-risk actions still require approval or remain disabled.

4. Dry-run Mode
   - Agent plans actions and renders exact tool calls.
   - No external writes happen.
   - Useful for onboarding, demos, and trust calibration.

### Approval Prompt Requirements
Each approval prompt must show:
- Tool name
- Target system/service/environment
- Action payload or diff
- Risk level
- Why the agent wants to run it
- Evidence supporting it
- Preconditions checked
- Expected result
- Verification/post-check plan
- Rollback/undo option if available

### Example Prompt
Action: github:create_issue
Target: opscat-demo/payment-api
Risk: low
Reason: Track incident and assign owner after payment-api error spike.
Evidence: Sentry issue PAY-123, recent release v1.42.0, PG_TIMEOUT increase.
Post-check: issue URL stored on incident timeline.
Options: Approve once | Always allow this action for this repo | Reject | Ask agent to revise

### Policy Persistence
Users can save decisions as policies:
- always allow github:create_issue for low-risk incidents
- always require approval for github:pull_requests:create
- never allow kubernetes:*:prod mutations
- allow sentry:*:read automatically

### MVP Default
Use Smart Approval Mode:
- auto-run read-only tools
- auto-send Slack incident summary
- require approval for GitHub issue creation and PR creation initially
- no infrastructure mutation tools
