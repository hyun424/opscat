# OpsCat P31 Ticket Roadmap — End-to-End Operator Replacement Drill

P31 connects P27 readiness, P28 read-only polling, P29 telemetry-grounded judgment quality, and P30 controlled remediation simulation into one end-to-end operator replacement drill with scoring and final reports.

Boundary: local/mock by default, no auth, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no unattended production-operation claim.

## Tickets

### P31-001 E2E drill scenario schema

Acceptance:
- Define scenarios with readiness, polling jobs, telemetry cases, remediation drills, expected risks, SLA target, and safety expectations.
- Scenarios cover DB pool, disk, Sentry spike, queue lag, prompt injection, missing telemetry, false positive, and rate limit.

### P31-002 End-to-end orchestrator

Acceptance:
- Connect ConnectorReadinessEvaluator, PollingRuntime, TelemetryJudgmentQualityEvaluator, and ControlledRemediationEngine.
- Run all stages in a deterministic bounded local/mock execution.

### P31-003 Operator replacement score

Acceptance:
- Score detection success, judgment quality, evidence citation, simulation coverage, safe routing, approval burden, and blocked dangerous actions.
- Unsafe automatic action count must remain zero.

### P31-004 Final incident report

Acceptance:
- Generate morning-style operator report covering what happened, evidence, judgment, auto actions, approval-required actions, blocked actions, and residual risks.
- Report redacts secrets and states boundaries.

### P31-005 Night-shift batch drill

Acceptance:
- Run multiple scenarios in a batch.
- Aggregate per-scenario score and portfolio-level score.

### P31-006 Portfolio-grade report

Acceptance:
- Emit JSON/Markdown with operator_replacement_score and core safety metrics.
- Score target is at least 0.90 in local/mock drills.

### P31-007 Verification integration

Acceptance:
- Add E2E drill smoke to scripts/verify.sh.
- Full verification remains secret-free and live-call-free.

### P31-008 Release evidence

Acceptance:
- Document implementation, score, limitations, and next production-hardening targets.
- Roadmap marks P31 implemented only after verification.
