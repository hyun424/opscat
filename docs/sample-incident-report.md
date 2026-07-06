# Incident Report: incident-demo-payment-api-001

> Representative sample matching `app/services/report_service.py` output shape. It is not generated from the current leader head because the current app import is blocked by an indentation syntax error; see `integration-verification.md`.

- Status: resolved
- Service: payment-api
- Environment: staging
- Severity: high
- Summary: Payment API timeout spike started shortly after deployment `payment-api@2026.07.06.1`.
- Root cause candidate: Recent deploy changed checkout timeout handling and increased upstream payment gateway retries.
- Confidence: 0.86

## Evidence

- `ev-error-001` sentry_issue: Timeout errors increased from baseline 0.3% to 8.7% for `/checkout/submit` after the deployment window.
- `ev-deploy-001` deploy: Release `payment-api@2026.07.06.1` was deployed to staging 12 minutes before the alert.
- `ev-runbook-001` runbook: Payment API timeout runbook recommends rollback PR draft when timeout rate exceeds 5% after a deploy.
- `ev-prior-001` prior_incident: Similar staging regression on 2026-06-18 resolved after reverting checkout timeout middleware.

## Actions

- `act-rollback-pr-001` mock.create_rollback_pr status=executed risk=medium policy=REQUIRE_APPROVAL
  - Rationale: Evidence links the timeout spike to a recent staging deploy; rollback is reversible and should be reviewed before merge.
  - Post-checks: confirm timeout rate below 1%, confirm checkout success rate recovered, confirm no new critical errors for 10 minutes
  - Execution result: {'status': 'success', 'mock_pr_url': 'https://example.invalid/mock/payment-api/rollback-pr-001', 'external_side_effects': false}
- `act-verify-001` mock.verify_recovery status=executed risk=read_only policy=ALLOW
  - Rationale: Verify recovery after mock rollback PR action.
  - Post-checks: timeout rate below threshold, synthetic checkout passes
  - Execution result: {'status': 'success', 'timeout_rate': '0.4%', 'synthetic_checkout': 'passed'}

## Timeline

- 2026-07-06T17:00:00+00:00 [system] alert_received: Mock alert received for payment-api staging timeout spike.
- 2026-07-06T17:00:02+00:00 [agent] context_gathered: Collected error, deploy, runbook, and prior incident evidence.
- 2026-07-06T17:00:04+00:00 [agent] action_proposed: Proposed mock.create_rollback_pr with medium risk and approval required.
- 2026-07-06T17:00:20+00:00 [human] action_approved: demo-user approved rollback PR draft.
- 2026-07-06T17:00:22+00:00 [integration] action_executed: Mock rollback PR draft created locally with no external side effects.
- 2026-07-06T17:00:30+00:00 [agent] recovery_verified: Mock recovery checks passed.
- 2026-07-06T17:00:31+00:00 [system] incident_resolved: Incident marked resolved and report generated.
