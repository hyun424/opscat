# P9 Tickets — Autonomous Incident Commander

Source roadmap: `docs/operations/p9-ticket-roadmap.md`.

Execution must follow: plan -> plan review -> RED tests -> implementation -> GREEN verification -> integration verification.

## Ordered Tickets

- [P9-001 — Incident Commander Loop](p9-001-incident-commander-loop.md)
- [P9-002 — Multi-step Response Planner](p9-002-multi-step-response-planner.md) — depends on P9-001
- [P9-003 — Autonomy Readiness Score](p9-003-autonomy-readiness-score.md) — depends on P9-001, P9-002
- [P9-004 — Evidence Graph Model](p9-004-evidence-graph-model.md) — depends on P9-001
- [P9-005 — Recovery Verifier v2](p9-005-recovery-verifier-v2.md) — depends on P9-001, P9-002, P9-003
- [P9-006 — Learning Loop from Prior Outcomes](p9-006-learning-loop-prior-outcomes.md) — depends on P9-003, P9-005
- [P9-007 — Chaos Replay Tournament](p9-007-chaos-replay-tournament.md) — depends on P9-001, P9-003, P9-004, P9-005
- [P9-008 — Commander UI Panel](p9-008-commander-ui-panel.md) — depends on P9-001, P9-002, P9-003, P9-004, P9-005
- [P9-009 — Commander Safety Regression Pack](p9-009-commander-safety-regression-pack.md) — depends on P9-001, P9-003, P9-006, P9-007
- [P9-010 — P9 Release Evidence and Roadmap Closure](p9-010-release-evidence-roadmap-closure.md) — depends on P9-001, P9-002, P9-003, P9-004, P9-005, P9-006, P9-007, P9-008, P9-009

## Team Lane Mapping

- Lane A: P9-001 + P9-002 commander loop and response planner.
- Lane B: P9-003 + P9-004 readiness score and evidence graph.
- Lane C: P9-005 + P9-006 recovery verifier and learning loop.
- Lane D: P9-007 + P9-009 chaos tournament and safety regression pack.
- Lane E: P9-008 + P9-010 commander UI, docs, release evidence, final verification.

## Final Gate

`bash scripts/verify.sh --profile full` must pass from leader HEAD before P9 closure.
