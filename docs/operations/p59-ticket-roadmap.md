# OpsCat P59 Ticket Roadmap — Hybrid Commander Comparator

P59 compares deterministic candidate gates, local/mock LLM judgment, and a hybrid guarded commander lane so OpsCat can decide whether LLM reasoning improves the operator loop without weakening safety or regression guarantees.

## Tickets

- P59-001 — Deterministic lane: summarize candidate/real-dataset deterministic gates from P58 prerequisites.
- P59-002 — LLM lane: summarize mock LLM quality from P58 harness.
- P59-003 — Hybrid lane: combine deterministic guardrails with LLM explanation quality while preserving deterministic safety gates.
- P59-004 — Comparator gates: require hybrid to pass, safety to remain zero, and no lane to bypass action boundaries.
- P59-005 — CLI report: write JSON and Markdown artifacts for local review.
- P59-006 — Verification integration: wire P59 smoke into `scripts/verify.sh`.
- P59-007 — Release evidence: document artifacts, boundaries, and final verification result.

## Acceptance criteria

- P58 harness passes.
- Comparator includes deterministic, llm_mock, and hybrid_guarded lanes.
- Hybrid lane is selected as the recommended lane.
- Hybrid lane has score at least as high as the LLM lane and no lower than 0.95.
- Safety regressions and action executions remain zero.
- Boundary remains offline/local with no default external model/API calls, production mutation, remediation execution, or unattended production-operation claim.
