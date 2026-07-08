# OpsCat P38 Ticket Roadmap — Agent Evaluation Dashboard

P38 aggregates recent agentic safety/evaluation phases into one local dashboard artifact. It is a JSON/Markdown scorecard, not a hosted UI, and it does not call live services or execute remediation.

## Tickets

- P38-001 — Dashboard source manifest: define P33-P37 local source fixtures and phase labels.
- P38-002 — Metric adapters: normalize connector dry-run, polling, shadow mode, approval control, and OSS config hardening metrics.
- P38-003 — Portfolio scorecard: compute passed phase count, average score, boundary violation count, and readiness tier.
- P38-004 — Safety gates: assert no live API calls, no production mutation, no remediation execution, and no external model calls by default.
- P38-005 — Operator summary: render concise Markdown with phase cards and next-risk notes.
- P38-006 — Evidence links: include generated artifact paths for each phase.
- P38-007 — CLI report: `scripts/run_agent_evaluation_dashboard.py` writes JSON/Markdown reports.
- P38-008 — Verification integration: add targeted tests, full-profile smoke, release evidence, and docs contract tests.

## Boundaries

- no hosted dashboard requirement
- no auth/session work
- no live API calls
- no production mutation
- no remediation execution
- no unrestricted shell
- no default external model/API calls
- no unattended production-operation claim

## Acceptance criteria

- At least five phase cards are aggregated.
- All included phases pass their local gates.
- Boundary violation count is 0.
- Overall score is at least 0.9.
- Markdown contains operator-readable phase cards.
- Full verification profile includes `agent_evaluation_dashboard_smoke`.
