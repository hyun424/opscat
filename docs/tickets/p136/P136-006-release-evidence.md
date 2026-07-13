# P136-006 - Fixed release runner and evidence

## Scope

Implement the real fixed 50-case matrix, measured runtime authority guard,
resource accounting, current-source binding, independent review artifact, and
fail-closed release evidence.

## Acceptance

- The runner executes every case instead of self-stamping results.
- All 50 config/path, authority/reservation, duplicate/P135, partial/rotation,
  crash/durability, lease/exhaustion/failure/signal/guard cases carry exact
  expected semantics.
- Exact-key forbidden authority, runtime activity, evaluator activity, and
  resource maps independently revalidate; wall uses monotonic time, CPU uses
  self/child `getrusage`, and peak RSS is normalized to bytes.
- Exact errors, totals, provider coverage, crash/duplicate segment-read
  semantics, resources, and exact-zero authority independently revalidate.
- Status is `p136_incremental_local_observation_qualified` only when all gates
  pass.
