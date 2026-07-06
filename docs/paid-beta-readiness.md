# OpsCat Paid Beta Readiness Bar

This document defines the minimum bar before OpsCat can be shown as a paid-beta product rather than a portfolio-only MVP.

## Paid Beta Positioning
OpsCat is not a full observability replacement. It is a safe AI on-call agent that connects to existing alerting/observability systems, investigates incidents, proposes or executes policy-approved actions, verifies recovery, and leaves an audit trail.

## Minimum Paid-Beta Capabilities

### 1. Team/tenant model
- Workspace/tenant boundary exists in data model or implementation plan.
- Every incident, evidence item, action, policy, and integration belongs to a tenant/workspace.
- No cross-tenant data access in API/service layer.

### 2. Permission and policy model
- Capabilities are granular, not broad admin tokens.
- Policy decisions are deterministic: ALLOW, REQUIRE_APPROVAL, DENY, ESCALATE.
- All mutation actions require capability checks.
- Production-impacting actions are denied or approval-gated by default.

### 3. Auditability
- Every tool/action proposal is recorded.
- Every approval/rejection has actor, timestamp, target, and payload/diff.
- Every executed action has post-checks and outcome.
- Incident timeline is exportable.

### 4. Data boundary and privacy
- Raw logs are not bulk-ingested by default.
- Evidence is minimized and redacted before LLM use.
- Secret/PII redaction exists and is tested.
- Self-hosted connector architecture is documented.

### 5. Product reliability
- Webhook handling is idempotent.
- Duplicate alerts are grouped or documented as a near-term gap.
- Tool execution is idempotent or protected by action state.
- Failure paths escalate instead of silently failing.

### 6. Customer-facing onboarding
- README has a clear 5-minute local demo.
- Docs explain what permissions OpsCat needs and why.
- Docs explain safe defaults and Night Autopilot boundaries.
- Sample incident report shows the value clearly.

### 7. Verification
- Core tests pass locally.
- Safety regression tests pass.
- Demo script works without external credentials.
- Docker Compose config validates.
- Known gaps are explicit and not hidden.

## Not Required for First Paid Beta
- Full Datadog/Loki/Sentry/GitHub/Slack production integrations.
- Production rollback execution.
- Billing implementation.
- Full UI polish.
- Multi-cloud production deployment.

## Required Before Charging Real Customers
- Authentication and tenant-scoped authorization.
- Encrypted integration token storage.
- Real connector deployment story.
- Basic web UI or Slack-first approval UI.
- Hosted or self-hosted deployment guide.
- Security review and threat model.
- Support and incident handling process for OpsCat itself.
