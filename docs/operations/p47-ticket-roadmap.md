# OpsCat P47 Ticket Roadmap — Tool Selection Planner

P47 turns investigation requests into safe read-only tool plans. It maps hypotheses to observability queries while blocking production mutation, shell execution, and remediation.

## Tickets

- P47-001 — Tool catalog: define allowed read-only Grafana/Datadog/Sentry/deploy/log tools and blocked mutation tools.
- P47-002 — Planner: map P46 next investigations to concrete tool calls.
- P47-003 — Safety validator: reject shell, write, restart, rollback, delete, and production mutation tools.
- P47-004 — Evidence references: preserve hypothesis IDs and evidence links for every selected tool.
- P47-005 — Approval policy: route non-read-only or low-confidence plans to human approval/block.
- P47-006 — CLI report: emit selected tools, blocked tools, and safety metrics.
- P47-007 — Verification integration: add offline smoke to `scripts/verify.sh`.
- P47-008 — Release evidence: document metrics and boundaries.
