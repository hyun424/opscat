# G006/P105-RQ Qualification-Capacity Amendment Plan

Plan source:
`docs/operations/p105-g006-qualification-capacity-amendment.md`.
Test-spec source:
`docs/operations/p105-g006-qualification-capacity-test-spec.md`.

## Scope

Documentation-only correction of a mathematically impossible evidence-capacity
program. Existing release floors and safety boundaries remain unchanged.

## Ordered delivery

1. Record the exact baseline maximum and deficit.
2. Independently review the conventional 256-service, one-hour database/queue/
   deploy actual-runtime fleet profile.
3. Add RED tests only after approval.
4. Implement without changing legacy exact profiles.
5. Execute two full actual runs per family and verify receipts/reproducibility.
6. Materialize central evidence, benchmark, independently review, and fully
   verify before P106.

## Acceptance

- No floor lowering, scorer-targeted duration, cloned incident, rerun credit,
  fixed coverage, synthetic padding, auth, credential read, production mutation,
  action planning, or action execution.
- Queue/deploy source-window labels and observed service intervals are exact,
  deduplicated, and receipt-bound.
- P106 remains locked until the unchanged release gate passes.
