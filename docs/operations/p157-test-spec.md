# P157 Test Specification

1. Reject stale P156 evidence, unknown actions, non-lab targets, missing
   rollback handlers, and forged pre-state hashes.
2. Execute fixed lab actions, compare postconditions, and roll back harmful or
   uncertain outcomes.
3. Measure verified recovery, harmful-action containment, rollback closure, and
   false recovery.
4. Preserve exact-zero production mutation and bind final artifacts.
