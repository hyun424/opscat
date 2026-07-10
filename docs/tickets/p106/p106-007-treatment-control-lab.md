# P106-007 - Treatment/Control Lab

## Goal

Provide an offline pre-incident planning lab that verifies benchmark arms start
from the same public pre-treatment state before any scoring.

## Contract

- `initial_condition_fingerprint` is derived from the complete public initial
  state and deterministic seed.
- Arm name, selected action, and scorer-only labels are excluded.
- Cohort interference, telemetry loss, natural recovery, noisy false positives
  without denominator, and unequal starting fingerprints fail before planner or
  scorer execution.

## Acceptance

The lab emits byte-identical canonical initial-state payloads and identical
recomputed fingerprints for comparable arms. Any arm-specific pre-treatment
mutation fails the case before regret or harm metrics are computed.
