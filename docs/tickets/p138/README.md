# P138 Tickets

Execute in dependency order:

1. [P138-001](P138-001.md) - exact contracts, paths, and counters
2. [P138-002](P138-002.md) - reconciliation-first phase machine and P136 two-phase outcome
3. [P138-003](P138-003.md) - publisher lease, split-commit recovery, and lock order
4. [P138-004](P138-004.md) - delta, genesis bootstrap, authority, and leak guards
5. [P138-005](P138-005.md) - exact 30-case real-boundary runner
6. [P138-006](P138-006.md) - frozen release evidence and verification profile
7. [P138-007](P138-007.md) - documentation and operator boundary
8. [P138-008](P138-008.md) - independent review and release handoff

Acceptance gates:

- Observe each implementation ticket's contract tests fail for the intended
  reason before implementing it. Do not start a dependent ticket until its
  predecessor's targeted pytest, Ruff, Mypy, and applicable component checks
  are green.
- Keep P138 reconciliation-first. Acquire its lease before coordinated reads;
  finish a current publisher/P137/P138 state transition before permitting one
  new real `observe_one_cycle`. Never encode unconditional
  `P136 -> publish -> P137` sequencing.
- Preserve ownership: P136 alone observes and owns the durable
  `p136.cycle_outcome_intent.v1` -> checkpoint ->
  `p136.cycle_completion.v1` sequence; the leased P136-owned publisher alone
  writes the fixed handoff; P137 alone validates and triages; P138 coordinates
  phases and records hashes/statuses.
- Preserve the exact six-phase machine, the empty-delta short path, P136
  same-cycle two-phase outcome recovery, complete publisher split-commit recovery,
  genesis-only bootstrap, contiguous new-promotion delta, and sole lock order
  defined by the roadmap.
- Preserve the shared exact 15-key zero `forbidden_authority` tuple and the
  roadmap's exact runtime/evaluator maps. Missing/extra keys, aliases,
  booleans, negatives, or nonzero forbidden values fail closed.
- Preserve no authentication, provider/live-connector, network/DNS/socket,
  credential or environment read, subprocess/shell, runtime signal,
  notification/delivery, action/remediation, staging/production mutation, or
  operator-replacement authority. P138 is a finite local supervisor, not
  unattended production operation.
- Reuse P136/P137 fixtures and evidence without duplicating or re-claiming
  their canonical denominators. The P138 denominator is exactly 30/30; the
  required real-boundary cases may not be replaced by callback-only proof.
  CASE-21/22 cover the post-checkpoint/pre-completion P136 outcome state;
  CASE-29/30 cover the post-intent/pre-checkpoint state.
- Do not wire `p138-release` until the exact 30-case runner and targeted tests
  are stable.
- Preliminary and final use the same tracked paths:
  `evals/p138/output/canonical-matrix.json`,
  `evals/p138/output/freeze-manifest.json`,
  `evals/p138/output/release-evidence.json`, and
  `evals/p138/final-implementation-review.json`. Final mode regenerates no
  reviewed input.
- Release requires exact status
  `p138_local_observation_to_triage_supervisor_qualified`, 30 expected/30
  passed/0 failed, exact rebuilt counters, zero unresolved P0/P1/P2 review
  findings, separate P136/P137 profiles, docs/full checks, authority/leak scans,
  and `git diff --check`. Until those artifacts and checks exist, P138 remains
  unqualified and is not unattended production operation.
