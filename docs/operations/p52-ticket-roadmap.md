# OpsCat P52 Ticket Roadmap — Failure Mining Loop

Goal: turn benchmark failures into concrete improvement tickets and regression cases so the agent improves from measured weaknesses instead of vague impressions.

## Tickets

- P52-001 — Failure mining input: consume the P51 benchmark fixture/report and preserve case-level failure evidence.
- P52-002 — Failure taxonomy grouping: group failures by detection, root-cause, evidence, route, re-ranking, and recovery-verification buckets.
- P52-003 — Improvement ticket generation: generate priority, owner lane, acceptance criteria, and safety boundary for each failure cluster.
- P52-004 — Regression case generation: create deterministic regression cases linked to failing benchmark cases.
- P52-005 — Deduplication and prioritization: avoid duplicate tickets and rank by severity/frequency/operator risk.
- P52-006 — CLI report: emit JSON/Markdown artifacts for the improvement loop.
- P52-007 — Verification integration: wire full-profile smoke and docs contract test.
- P52-008 — Release evidence: document mined tickets, regression cases, verification, and remaining safety boundary.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
