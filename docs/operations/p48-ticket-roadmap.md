# OpsCat P48 Ticket Roadmap — Hypothesis Re-ranking

P48 re-ranks hypotheses after read-only investigation results arrive. It updates support/counter/missing evidence, confidence, and action gates instead of anchoring on the initial guess.

## Tickets

- P48-001 — Re-ranking fixture: define before/after investigation observations.
- P48-002 — Evidence update model: merge new read-only tool results into hypothesis support/counter/missing fields.
- P48-003 — Re-ranker: recompute confidence and priority, allowing top hypothesis changes.
- P48-004 — Anti-anchoring checks: record when initial top hypothesis is demoted by counter-evidence.
- P48-005 — Conservative action gate: block action when top confidence is low or evidence conflicts.
- P48-006 — CLI report: emit before/after ranking and deltas.
- P48-007 — Verification integration: add offline smoke to `scripts/verify.sh`.
- P48-008 — Release evidence: document metrics and limits.
