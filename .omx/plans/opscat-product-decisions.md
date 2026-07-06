# OpsCat Product & Architecture Decisions

This document captures detailed product decisions that should guide future AI-assisted implementation.

## 1. Product Identity

### Core definition
OpsCat is an agentic operations automation system. It watches incident signals, investigates with tools, proposes or executes remediations according to policy, verifies recovery, and leaves an audit trail.

### What OpsCat is
- AI on-call first responder
- Incident investigation agent
- Runbook execution assistant
- Approval-gated operations automation platform
- Observability-context reasoning layer

### What OpsCat is not
- A generic chatbot
- A full observability database replacement
- A log storage product
- A production mutation bot with unrestricted admin access
- A desktop-first app

## 2. Primary User Personas

### Engineering Manager / CTO
Wants fewer noisy alerts, faster incident response, lower on-call burden, and clear auditability.

### On-call Engineer
Wants context, evidence, likely cause, safe next action, and fewer manual lookups across tools.

### SRE / Platform Engineer
Wants policy controls, integrations, safe automation, runbook consistency, and post-incident reports.

### Security / Compliance Reviewer
Wants least privilege, data minimization, redaction, approval logs, and evidence of who/what changed what.

## 3. Product Modes

### Dry-run Mode
- No external writes.
- Agent proposes exact tool calls and expected effects.
- Best for onboarding, demos, and trust building.

### Manual Approval Mode
- Read-only tools can run automatically.
- Every mutation/write tool requires approval.

### Smart Approval Mode
- Default MVP mode.
- Read-only tools run automatically.
- Low-risk allowlisted writes can run automatically.
- Medium/high-risk actions require approval.

### Autopilot Mode
- Allowlisted actions can execute automatically.
- Strong policy enforcement required.
- High-risk actions remain approval-gated or disabled.

## 4. Deployment Model

### MVP local mode
- Docker Compose.
- FastAPI API.
- PostgreSQL.
- Mock alert/log/deploy data.

### SaaS mode
- OpsCat Cloud hosts control plane.
- Customer-side connector runs inside customer environment.
- Raw logs stay in customer environment by default.

### Enterprise/private mode
- Fully self-hosted inside customer VPC/Kubernetes.
- Suitable for finance, public sector, healthcare, and sensitive production systems.

## 5. Data Boundary Principles

- Do not ingest all raw logs by default.
- Query only incident-relevant windows.
- Redact secrets, tokens, PII, and customer data before LLM input.
- Store source links, hashes, timestamps, and minimal evidence snippets.
- Keep full raw evidence in customer observability tools where possible.
- Make cloud upload optional and configurable.
- Provide self-hosted mode for sensitive customers.

## 6. Permission Model

### Capability-based permissions
Use granular capability grants rather than broad roles.

Examples:
- sentry:issues:read
- sentry:events:read
- github:commits:read
- github:issues:write
- github:pull_requests:write
- slack:messages:write
- kubernetes:pods:read
- kubernetes:deployments:restart:staging
- feature_flags:toggle:approved_flags_only

### Policy check inputs
Every tool call must be checked against:
- tenant policy
- integration policy
- service policy
- environment policy
- incident severity
- action risk level
- approval status
- requester identity
- current incident state

## 7. Action Risk Classification

### Read-only
- Query logs.
- Query Sentry issue.
- Query commits/releases.
- Query metrics.
- Read runbooks.

### Low risk
- Send Slack summary.
- Create incident ticket.
- Add timeline note.
- Create postmortem draft.
- Silence duplicate alert for a short bounded duration.

### Medium risk
- Create rollback PR.
- Toggle explicitly approved feature flag.
- Restart non-production service.
- Scale non-critical worker.

### High risk
- Production rollback.
- Production service restart.
- Traffic rerouting.
- Cloud infra mutation.
- Security group/IAM/policy changes.

### Prohibited by default
- Database writes/migrations.
- Data deletion.
- Payment/settlement mutation.
- Secrets access.
- Unbounded shell execution.
- Any production mutation without explicit policy.

## 8. Agent Loop Contract

The agent should follow this loop:
1. Observe incident signal.
2. Classify service, severity, environment, and suspected domain.
3. Gather context using read-only tools.
4. Generate hypotheses.
5. For each hypothesis, gather supporting/refuting evidence.
6. Select recommended action.
7. Run guardrail and policy check.
8. Ask for approval or execute if policy allows.
9. Verify outcome.
10. Update memory and report.

The agent must not jump from alert to mutation without investigation and policy check.

## 9. Agent Output Requirements

Every incident analysis should include:
- concise summary
- affected service/environment
- severity estimate
- timeline
- top hypotheses
- evidence for each hypothesis
- confidence level
- recommended action
- action risk level
- required approval status
- expected impact
- verification plan
- escalation condition

Every action proposal should include:
- exact tool/action name
- target system
- target environment
- payload/diff
- rationale
- evidence references
- preconditions checked
- risk level
- approval requirement
- expected result
- rollback/undo option if available
- post-checks

## 10. Human Interaction UX

### Approval prompt options
- Approve once
- Reject
- Ask agent to revise
- Always allow this action under current scope
- Always require approval for this action
- Never allow this action

### Incident controls
- More investigation
- Show evidence
- Show raw source links
- Escalate to human owner
- Create issue
- Draft PR
- Mark resolved
- Mark false positive

### Trust-building UI
- Show agent reasoning as evidence-backed steps.
- Avoid hidden autonomous writes.
- Every action should be traceable.
- Policies should be visible and editable.

## 11. Integrations Roadmap

### Phase 1
- Mock alert source
- Mock Sentry
- Mock GitHub
- Mock Slack output

### Phase 2
- Slack real messages/interactions
- GitHub issue/PR API
- Sentry real webhook/API

### Phase 3
- Grafana/Loki
- Datadog
- CloudWatch
- PagerDuty/Opsgenie
- Linear/Jira

### Phase 4
- Kubernetes read-only
- Feature flag providers
- CI/CD providers
- Terraform plan generation

### Phase 5
- Approved low-risk remediation execution
- Self-hosted connector
- Enterprise policy engine

## 12. Runbook Design

Runbooks should be machine-readable YAML/JSON plus optional human markdown.

Runbook fields:
- service
- owner
- severity mapping
- signals
- diagnostic steps
- known causes
- safe actions
- dangerous actions
- escalation policy
- verification checks
- rollback plan
- related dashboards
- related repositories

The agent should match incidents to runbooks before proposing actions.

## 13. Incident State Machine

Suggested states:
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

State transitions should be explicit and persisted.

## 14. Memory Model

OpsCat should remember:
- past incidents
- past root causes
- actions that worked
- actions that failed
- false positive patterns
- service ownership
- runbook changes
- user policy preferences

Memory must be scoped by tenant and service.

## 15. Evaluation Strategy

### Golden scenarios
Create curated incident scenarios:
- bad deploy causes new exception
- external API timeout
- DB connection pool exhaustion
- background worker stuck
- queue backlog
- noisy false positive alert
- duplicate alert storm

### Metrics
- correct service classification
- correct top-1/top-2 cause
- evidence completeness
- unsafe action rejection rate
- time to first useful summary
- approval prompt clarity
- recovery verification success

### Safety evals
- Does not suggest DB deletion.
- Does not expose secrets.
- Does not run prohibited prod action.
- Requires approval for configured actions.
- Escalates when confidence is low.

## 16. Security Requirements

- OAuth/token storage encrypted at rest.
- No secrets in prompts.
- Secret scanning/redaction before model call.
- Full audit log for tool calls.
- RBAC for admin/user/viewer roles.
- Tenant isolation.
- Least-privilege integration scopes.
- Allow self-hosted connector.
- Support data retention settings.

## 17. Reliability Requirements

- Agent jobs should be idempotent.
- Webhook handling should retry safely.
- Duplicate alerts should be grouped.
- Tool failures should degrade gracefully.
- No action should be executed twice accidentally.
- Long-running investigations should checkpoint state.
- Approval should expire after configurable timeout.

## 18. Observability for OpsCat Itself

OpsCat must monitor itself:
- agent job latency
- tool call success/failure
- LLM cost and token usage
- approval latency
- action execution success
- incident resolution time
- policy denials
- redaction events

## 19. MVP Acceptance Criteria

The MVP is good enough when:
- A mock alert creates an incident.
- Agent gathers mock error/deploy/runbook context.
- Agent produces evidence-backed hypotheses.
- Agent proposes a safe action with risk level.
- Policy engine decides whether approval is needed.
- User can approve/reject action.
- Approved GitHub issue/PR action is executed in test mode.
- Incident report and timeline are generated.
- Unsafe/prohibited action is blocked.

## 20. Important Non-Goals for Early Build

- Do not build a full observability backend.
- Do not implement arbitrary shell execution.
- Do not support production auto-rollback early.
- Do not overbuild UI before the agent loop works.
- Do not integrate every tool at once.
- Do not store unredacted raw logs in the cloud by default.

## 21. Recommended First Engineering Sequence

1. FastAPI scaffold.
2. Database models.
3. Incident state machine.
4. Mock alert endpoint.
5. Mock tools.
6. Agent output schema.
7. Policy engine.
8. Terminal/API approval flow.
9. Slack approval flow.
10. GitHub issue action.
11. GitHub PR draft action.
12. Sentry integration.
13. Report generation.
14. Demo scripts.

## 22. Default Product Principle
When in doubt, choose trust over autonomy. OpsCat should earn automation rights gradually through evidence, policy, and verified outcomes.

## 23. Night Autopilot Mode

### User Need
Users want OpsCat to take safe action while they sleep, not merely summarize incidents. The product should reduce night-time wakeups by automatically handling known, bounded, reversible incidents.

### Decision
Add Night Autopilot Mode: a scheduled policy mode that can execute pre-approved low-risk remediations during configured quiet hours, verify recovery, and escalate only when needed.

### Quiet Hours Policy
Users/admins can configure:
- timezone
- quiet hour window
- services covered
- environments covered
- maximum action risk allowed
- maximum number of automatic attempts per incident
- escalation contacts
- wake-up thresholds

### Actions Allowed During Night Autopilot
Default allowed examples:
- create incident ticket
- group/deduplicate alerts
- send Slack/PagerDuty update
- restart non-prod worker
- scale approved worker pool within bounds
- toggle approved kill-switch feature flag
- execute known runbook step marked reversible
- create rollback PR, but not merge/deploy it unless explicitly allowed

### Actions Not Allowed by Default
- production rollback
- database mutation
- security/IAM changes
- cloud resource deletion
- arbitrary shell command
- payment/settlement mutation
- any action without post-check

### Required Conditions for Automatic Night Action
All must pass:
- incident matches a known runbook or golden scenario
- confidence exceeds configured threshold
- action is allowlisted for service/environment/time window
- action is reversible or has bounded blast radius
- preconditions are verified
- no active freeze window blocks the action
- post-check is defined
- escalation path is configured

### Verification Loop
After automatic action:
1. Wait configured cooldown.
2. Re-check alert/error/metric status.
3. If recovered, mark resolved and send morning report.
4. If not recovered, try next allowlisted action if attempts remain.
5. If still unresolved or higher severity detected, escalate/wake human.

### Morning Report
At the end of quiet hours, OpsCat should summarize:
- incidents detected
- actions taken
- evidence and reasoning
- whether each action worked
- any unresolved risks
- suggested follow-up PRs/runbook updates

### UX
Night Autopilot setup should be explicit and conservative:
- “Let OpsCat handle these known issues while I sleep.”
- Preview exactly what actions are allowed.
- Simulate last 30 days of incidents in dry-run mode before enabling.
- Require admin confirmation for production-affecting actions.

### MVP Implementation
Implement simulated Night Autopilot first:
- quiet hours config
- allowlisted mock actions
- max attempts
- verification check
- escalation simulation
- morning report generation
