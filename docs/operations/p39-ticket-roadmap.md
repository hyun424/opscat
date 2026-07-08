# OpsCat P39 Ticket Roadmap — Runbook Learning Loop

P39 converts recent local evaluation failures, blocked routes, degraded connectors, and approval-heavy decisions into runbook improvement recommendations and regression cases. It does not edit production runbooks automatically.

## Tickets

- P39-001 — Learning source manifest: define local sources from P33, P35, P36, P37, and P38.
- P39-002 — Signal extraction: collect degraded connectors, blocked shadow actions, approval-required actions, and dashboard risk notes.
- P39-003 — Recommendation generator: create runbook improvement recommendations with source evidence and owner category.
- P39-004 — Regression case generator: create deterministic regression scenarios for future evals.
- P39-005 — Safety gates: prevent unsafe learning, prompt-injection propagation, real secret capture, production mutation, and auto-application.
- P39-006 — Scorecard: report recommendation count, regression case count, source coverage, unsafe learning count, and applied change count.
- P39-007 — CLI report: `scripts/run_runbook_learning_loop.py` writes JSON/Markdown reports.
- P39-008 — Verification integration: add targeted tests, full-profile smoke, release evidence, and docs contract tests.

## Boundaries

- no automatic production runbook edits
- no auth/session work
- no live API calls
- no production mutation
- no remediation execution
- no unrestricted shell
- no default external model/API calls
- no unattended production-operation claim

## Acceptance criteria

- At least four recommendations are generated.
- At least three regression cases are generated.
- Source phase count is at least four.
- Unsafe learning count is 0.
- Applied change count is 0.
- Full verification profile includes `runbook_learning_loop_smoke`.
