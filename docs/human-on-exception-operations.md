# Human-on-Exception Operations Model

OpsCat's core promise is not “AI writes summaries.” The promise is:

> A team should not need a human staring at dashboards or triaging every alert. OpsCat handles routine monitoring and first response, and wakes a human only when judgment, authority, or risk requires it.

## Operating Principle
OpsCat replaces continuous human monitoring, not human accountability.

Humans should be needed for:
- high-risk production mutations,
- low-confidence incidents,
- customer-critical or data-critical impact,
- repeated failed remediation attempts,
- security/payment/auth incidents,
- ambiguous multi-system failures.

OpsCat should handle automatically:
- alert intake,
- deduplication/grouping,
- service/severity classification,
- context collection,
- evidence-backed hypothesis generation,
- known runbook matching,
- safe allowlisted remediation,
- post-action verification,
- incident timeline/report generation,
- morning/shift reports.

## Required Control Loop
Every incident must pass through this loop:

1. Detect signal.
2. Classify impact and service ownership.
3. Gather context with read-only tools.
4. Match runbook or known scenario.
5. Score confidence and risk.
6. Decide: auto-handle, approval-gate, deny, or escalate.
7. Execute only policy-allowed actions.
8. Verify recovery.
9. Retry bounded safe actions if allowed.
10. Escalate if unresolved, uncertain, or high impact.
11. Produce audit trail and report.

## No Silent Failure Rule
OpsCat must never fail quietly. If it cannot confidently investigate, act, or verify, it must escalate.

Escalation triggers:
- missing required context,
- confidence below threshold,
- no matching runbook for non-trivial incident,
- action policy denies all useful remediation,
- post-check fails,
- max attempts reached,
- incident severity increases,
- protected domain involved: payments, auth, security, data integrity.

## Night Autopilot Requirements
Night Autopilot is allowed only when:
- the incident matches a known runbook/scenario,
- action risk is within the quiet-hours policy,
- action is reversible or bounded,
- post-check is defined,
- max attempts are configured,
- escalation contact is configured,
- morning report is generated.

## Human Wake-Up Contract
If OpsCat wakes a human, it must include:
- what happened,
- affected service/env,
- current severity,
- customer/business impact estimate,
- evidence collected,
- hypotheses and confidence,
- actions already taken,
- actions blocked and why,
- recommended next action,
- direct links to source evidence/report.

## Product Metrics
OpsCat should optimize for:
- alert-to-summary time,
- alert-to-safe-action time,
- false wake-up rate,
- missed escalation rate,
- auto-resolved known incidents,
- failed auto-action rate,
- mean time to verify recovery,
- percentage of incidents with complete timeline/report.

## Paid Product Bar
A customer should be able to trust OpsCat for first-line operations only when:
- safe-action allowlists are explicit,
- escalation policies are configured,
- reports prove what happened overnight,
- every automated action has audit evidence,
- all high-risk cases wake humans instead of guessing.
