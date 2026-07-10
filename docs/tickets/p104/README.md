# P104 - Evidence Gap Investigator

P104 adds a tests-first evidence sufficiency layer between P103's bounded
read-only diagnostic episode and P100's deterministic action boundary.

Boundary: no auth, no production mutation, no mutating diagnostics, no provider
action authority, and no scorer-truth leakage.

## Tickets

- [P104-000 - Shared decision envelope](p104-000-shared-decision-envelope.md)
- [P104-001 - Evidence requirement contract](p104-001-evidence-requirement-contract.md)
- [P104-002 - Evidence state model](p104-002-evidence-state-model.md)
- [P104-003 - Partial/conflicting evidence lab](p104-003-partial-conflicting-evidence-lab.md)
- [P104-004 - Sufficiency hard gates](p104-004-sufficiency-hard-gates.md)
- [P104-005 - Information-value tool selection](p104-005-information-value-tool-selection.md)
- [P104-006 - Strict LLM gap proposal](p104-006-strict-llm-gap-proposal.md)
- [P104-007 - Budgets and fail-closed controls](p104-007-budget-and-fail-closed-controls.md)
- [P104-008 - Escalation payload](p104-008-escalation-payload.md)
- [P104-009 - Equal-state benchmark](p104-009-equal-state-benchmark.md)
- [P104-010 - CLI/docs/release integration](p104-010-cli-docs-release-integration.md)

## Phase Acceptance

- Every action-ready decision cites all critical requirements and evidence IDs.
- Contradictions, stale critical evidence, unavailable critical capabilities,
  and low telemetry block action handoff.
- Valid absence and no data/unavailable evidence are different states.
- Repeated tool execution, mutating diagnostics, provider action execution,
  production mutation, credential access, and scorer leakage remain zero.
- False-remediation handoff rate improves over P103 on partial/conflicting
  cases while retaining valid-case recovery within two percentage points.
