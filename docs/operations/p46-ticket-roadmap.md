# OpsCat P46 Ticket Roadmap — Investigator Loop

P46 adds an operator-like investigator loop: observe signals, generate hypotheses, collect support/counter/missing evidence, choose next investigations, and gate actions conservatively.

## Tickets

- P46-001 — Incident observation fixture: define multi-signal incidents requiring investigation.
- P46-002 — Hypothesis generator: produce deploy, DB, dependency, traffic, and false-positive hypotheses from evidence.
- P46-003 — Evidence binding: attach supporting/counter/missing evidence to every hypothesis using the P45 contract.
- P46-004 — Next investigation planner: list read-only queries/tools needed to confirm or refute each hypothesis.
- P46-005 — Action gate: block production execution; allow only read-only investigation and draft plans.
- P46-006 — Loop report: emit ranked hypotheses and investigation plans.
- P46-007 — Verification integration: add offline smoke to `scripts/verify.sh`.
- P46-008 — Release evidence: document metrics and limits.
