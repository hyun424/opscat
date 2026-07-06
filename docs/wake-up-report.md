# Human Wake-Up and Morning Report Contract

OpsCat's product promise is human-on-exception operations: humans should not continuously monitor dashboards, but they must be woken when judgment, authority, or risk requires it.

## Wake-up triggers

Wake a human when any of these occur:

- severity is critical or increases during handling;
- protected domain is involved: payments, auth, security, data integrity;
- confidence is below threshold;
- no matching runbook exists for a non-trivial incident;
- required context is missing;
- useful remediation is policy-denied;
- action risk exceeds quiet-hours policy;
- post-check fails;
- max attempts are reached;
- duplicate/related alerts suggest a wider outage.

## Wake-up packet

Every wake-up should include:

- what happened;
- affected service and environment;
- current severity and impact estimate;
- evidence collected with source links/IDs;
- hypotheses and confidence;
- actions already taken;
- actions blocked and why;
- recommended next action;
- direct link to incident report;
- escalation reason.

## Example wake-up packet

```markdown
# OpsCat Wake-Up: payment-api staging timeout spike

- Severity: high
- Reason for wake-up: medium-risk rollback PR requires approval and checkout timeout rate remains above threshold.
- Affected service: payment-api
- Environment: staging
- Customer impact: checkout submissions intermittently timeout in staging synthetic tests.
- Evidence:
  - ev-error-001: timeout rate increased to 8.7%
  - ev-deploy-001: deployment payment-api@2026.07.06.1 occurred 12 minutes before alert
  - ev-runbook-001: runbook recommends rollback review above 5% timeout rate
- Hypothesis: recent timeout middleware deploy caused retry amplification (confidence 0.86)
- Actions taken: read-only context gathered, rollback PR draft prepared locally
- Blocked action: mock.create_rollback_pr requires human approval
- Recommended next action: approve rollback PR draft or ask OpsCat for more investigation
- Report: data/mock_reports/incident-demo-payment-api-001.md
```

## Morning report

Night Autopilot must produce a morning report even when everything was handled automatically.

Minimum report fields:

- incidents detected;
- incidents auto-resolved;
- incidents escalated;
- actions attempted;
- actions blocked by policy;
- verification outcomes;
- unresolved follow-ups;
- safety limits hit;
- links to incident reports.

## No silent failure rule

If OpsCat cannot detect, classify, investigate, act, or verify confidently, it must escalate with evidence. A quiet failure is a product defect.
