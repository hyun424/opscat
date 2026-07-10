# P106 - Preventive Action Planner

P106 compiles a P105 release-qualified forecast and a P104 sufficient evidence
envelope into a ranked, simulation-only preventive plan. It uses the shared
action registry, policy engine, simulator, blast-radius service, and incident
memory before returning `plan`, `observe`, `escalate`, or
`blocked_fail_closed`.

Boundary: P106 adds no auth, no production mutation, no live remediation
execution, no production adapters, no credential use, no shell execution, and
no model action authority. Every output, including `PolicyDecision.ALLOW`, keeps
`execution_enabled=false`, `simulation_only=true`, and
`p107_required_for_execution=true`.

## Tickets

- [P106-000 - Release prerequisite and action-registry crosswalk](p106-000-release-prereq-action-registry-crosswalk.md)
- [P106-001 - Typed intervention contract and closed capability registry](p106-001-typed-intervention-contract.md)
- [P106-002 - Eligibility adapter and fallback semantics](p106-002-eligibility-fallback.md)
- [P106-003 - Expected-value scoring and baselines](p106-003-expected-value-baselines.md)
- [P106-004 - Shared safety gate](p106-004-shared-safety-gate.md)
- [P106-005 - Policy, simulation, blast-radius, and memory composition](p106-005-policy-simulation-memory-composition.md)
- [P106-006 - Canary, rollback, and post-check contract](p106-006-canary-rollback-postcheck-contract.md)
- [P106-007 - Treatment/control lab](p106-007-treatment-control-lab.md)
- [P106-008 - Optional LLM advisory](p106-008-optional-llm-advisory.md)
- [P106-009 - Adversarial benchmark and harm taxonomy](p106-009-adversarial-benchmark.md)
- [P106-010 - Approval profile integration without auth](p106-010-approval-profile-integration.md)
- [P106-011 - Release documentation and verification integration](p106-011-release-docs-verification.md)
- [P106-012 - Independent safety review and P107 gate lock](p106-012-independent-review-p107-gate.md)

## Phase Acceptance

- P105 eligibility comes from the canonical validator, not caller-provided
  booleans or copied release-gate fragments.
- P104 evidence must be `sufficient_for_policy_handoff`; stale, conflicting,
  unavailable, or naturally recovering evidence falls back to observe/escalate.
- Closed capabilities compile to `ActionRequest` plus `PolicyContext` through
  one shared `RiskEngine` graph.
- Expected value reports avoided impact, harm, cost, uncertainty, false-alert
  penalty, baseline selection, and tie-break trace.
- Shared policy, simulator, blast-radius, and incident-memory outputs appear in
  selected candidate traces.
- Optional LLM output is advisory only and may nominate registered
  capabilities; it cannot set expected value, override policy, change forecast
  probability, bypass gates, or unlock P107.
- The P107 gate remains blocked unless shared fail-closed coverage, exact zero
  harmful-action counts, and simulation-only mutation-plan evidence all pass in
  one fresh release evidence set.

## Evidence Status

The SHA-pinned real-derived P105 fixture produces fresh P106 evidence with
`scored=true`, one eligible planner evaluation, zero regret and harm, `1.0`
safe-fallback and fail-closed rates, one mutation-shaped simulation-only plan,
and exact zero authority. The prior verifier findings are fixed. The evidence
is eligible for P107 review, but P106 keeps `p107_unlocked=false`. Final
independent verdicts are code review `APPROVE`, architecture/safety `CLEAR`,
and verifier `PASS`.
