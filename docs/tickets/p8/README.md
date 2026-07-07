# P8 Tickets — AI Incident Responder War Room

Source roadmap: `docs/operations/p8-ticket-roadmap.md`.

Execution must follow: plan -> plan review -> RED tests -> implementation -> GREEN verification -> integration verification.

## Ordered Tickets

- [P8-001 — Incident War Room Read Model](p8-001-incident-war-room-read-model.md)
- [P8-003 — Agent Reliability Score v1](p8-003-agent-reliability-score-v1.md) — depends on P8-001
- [P8-004 — Runbook Critic and Improvement Suggestions](p8-004-runbook-critic.md) — depends on P8-001
- [P8-005 — Human Question Generator](p8-005-human-question-generator.md) — depends on P8-001, P8-003, P8-004
- [P8-002 — War Room API and Operator Console Panel](p8-002-war-room-api-operator-panel.md) — depends on P8-001, P8-003, P8-004, P8-005
- [P8-006 — Scenario Pack v2: Operator-Replacement Evals](p8-006-operator-replacement-eval-scenarios.md) — depends on P8-001, P8-003, P8-004, P8-005
- [P8-007 — War Room Report Export](p8-007-war-room-report-export.md) — depends on P8-001, P8-003, P8-004, P8-005
- [P8-008 — Operator Console Demo Polish](p8-008-operator-console-demo-polish.md) — depends on P8-002, P8-007
- [P8-009 — P8 Security and Threat Model Refresh](p8-009-security-threat-model-refresh.md) — depends on P8-001, P8-003, P8-004, P8-005, P8-002
- [P8-010 — P8 Release Evidence and Roadmap Closure](p8-010-release-evidence-roadmap-closure.md) — depends on P8-001, P8-002, P8-003, P8-004, P8-005, P8-006, P8-007, P8-008, P8-009

## Team Lane Mapping

- Lane A: P8-001 + P8-003 core war-room model and reliability score.
- Lane B: P8-004 + P8-005 runbook critic and human question generation.
- Lane C: P8-002 + P8-007 API/UI/report export.
- Lane D: P8-006 replay/eval scenario pack.
- Lane E: P8-008 + P8-009 + P8-010 demo, security docs, release evidence, full verification.

## Final Gate

`bash scripts/verify.sh --profile full` must pass from leader HEAD before P8 closure.
