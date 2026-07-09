# P91 Readiness Gap Remediation Planner Roadmap

P91 turns P90 safe auto-run readiness blockers into a prioritized, evidence-grounded remediation backlog. It states what to build next, what tests prove progress, which claims remain forbidden, and which local/shadow operating mode can be upgraded after each blocker is resolved.

## Tickets

- P91-001 - Model the remediation plan schema with plan ID, source readiness ID, prioritized items, claims still forbidden, human-gated items, audit metadata, and zero side-effect counters.
- P91-002 - Consume deterministic P90 readiness results with blockers, failed gates, component scores, allowed operating mode, and forbidden claims.
- P91-003 - Prioritize side-effect counter failures as emergency safety blockers before any mode upgrade.
- P91-004 - Prioritize missing evidence/reportability blockers as evidence and report tasks before readiness claims.
- P91-005 - Prioritize failed guardrails as failure-handling and rollback drill remediation before auto-run readiness claims.
- P91-006 - Prioritize high-severity human handoff as human approval policy remediation and keep it human-gated.
- P91-007 - Add CLI JSON/Markdown smoke output and wire the smoke into `scripts/verify.sh` plus release evidence.
- P91-008 - Publish conservative release documentation that frames P91 as a roadmap/planning artifact, not production autonomy.

## Boundary

P91 is a local/mock roadmap/planning artifact only. It models remediation backlog entries from fixture P90 readiness data. P91 does not call live APIs, read credentials, call networks, execute shell commands, sleep, spawn processes or agents, mutate production, execute remediation, execute actions, or claim production autonomy.
