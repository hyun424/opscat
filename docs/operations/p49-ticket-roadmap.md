# OpsCat P49 Ticket Roadmap — Remediation Verification Loop

Goal: convert a suspected remediation into an operator-safe loop: propose → pre-check → mock/draft execution boundary → post-check → verify recovery or escalate.

## Tickets

- P49-001 — Fixture: remediation candidates with recovered and non-recovered outcomes.
- P49-002 — Pre-check model: require blast-radius, confidence, and rollback/escalation metadata before action.
- P49-003 — Execution boundary: never perform production execution; only simulate or draft local actions.
- P49-004 — Post-check model: compare post-action evidence against recovery criteria.
- P49-005 — Failed verification route: escalate when post-check does not prove recovery.
- P49-006 — CLI report: JSON/Markdown output for portfolio evidence.
- P49-007 — Verification integration: full-profile smoke and docs contract test.
- P49-008 — Release evidence: final summary, roadmap, release evidence, and safety boundary.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
