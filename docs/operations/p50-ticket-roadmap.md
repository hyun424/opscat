# OpsCat P50 Ticket Roadmap — Night Operator Drill v2

Goal: run a local night-operator drill that chains evidence-grounded judgment, investigation, safe tool planning, re-ranking, and remediation verification without claiming production autopilot readiness.

## Tickets

- P50-001 — Drill fixture: night-mode incidents with expected safe outcomes.
- P50-002 — Evidence contract gate: every drill must pass P45-style support/counter/missing/action-boundary checks.
- P50-003 — Investigation gate: every drill must produce a top hypothesis and next read-only investigation plan.
- P50-004 — Tool plan gate: every drill must select read-only tools and block unsafe tools.
- P50-005 — Re-ranking gate: at least one drill must update/demote the initial hypothesis after observations.
- P50-006 — Remediation verification gate: at least one drill must verify recovery or escalation through P49.
- P50-007 — Readiness verdict: local night watch can be ready while unattended production readiness remains false.
- P50-008 — CLI/report/verification/release evidence wiring.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
