# OpsCat P60 Ticket Roadmap — Operator Replacement Readiness Gate

P60 aggregates P56-P59 evidence into an operator-replacement readiness gate. It can mark local/shadow operator replacement ready while explicitly blocking unattended production autonomy until live connector validation, auth/session controls, production execution controls, and human escalation contracts exist.

## Tickets

- P60-001 — Evidence aggregation: consume P59 hybrid comparator summary and upstream P56-P58 readiness signals.
- P60-002 — Local operator readiness: mark local/shadow operator replacement ready only when comparator, LLM harness, dataset bridge, and candidate regression gates pass.
- P60-003 — Production autonomy blocker model: keep unattended production readiness false with concrete blockers.
- P60-004 — Portfolio-grade scorecard: emit readiness level, recommended mode, strengths, and remaining gaps.
- P60-005 — CLI report: write JSON and Markdown artifacts for local review.
- P60-006 — Verification integration: wire P60 smoke into `scripts/verify.sh`.
- P60-007 — Release evidence: document artifacts, boundaries, and final verification result.

## Acceptance criteria

- P59 hybrid comparator passes.
- Local/shadow operator replacement readiness is true.
- Unattended production readiness is false.
- Recommended mode is `local_shadow_operator_replacement`.
- Blockers include live connector validation, auth/session controls, production execution controls, and human escalation contract.
- Safety regressions and action executions remain zero.
- Boundary remains offline/local with no default external model/API calls, production mutation, remediation execution, or unattended production-operation claim.
