# P137-008 - Canonical runner and CLI

## Scope

Implement the P137 canonical runner and local CLI for one-cycle and finite
bounded-foreground-loop validation against the fixed 60-case release matrix.

## Acceptance

- The runner executes exactly the 60 roadmap cases with explicit category, exact
  expected label or exact expected error, termination reason, classification
  scope, and named delta profile.
- Delta profiles materialize byte deltas as integers from
  `len(canonical_handoff_bundle_bytes)` and
  `sum(len(canonical_promotion_bytes))`; final evidence contains no symbolic
  byte placeholders.
- Delta-profile validation compares every materialized runtime key against the
  canonical `runtime_activity` schema and rejects legacy profile-only aliases.
  Profiles are exact full maps or source-bound exact overrides over the zero
  full map that materialize to full maps per row.
- Totals are independently rebuilt: 60 expected, 60 passed, 0 failed.
- All four classifications, all 15 request catalog entries, and all five P135
  provider profiles through P136 promotions are represented; OTLP is metrics.
- Resource limits use runner-measured monotonic wall, `getrusage` self+child CPU,
  and normalized matrix-interval peak RSS growth.
- The denominator includes explicit lease, bounded continuous mode, heartbeat,
  readiness, stale handoff, SIGINT/SIGTERM signal semantics, corrupt-state, CAS,
  rollback, same-sequence fork, previous-hash discontinuity, torn fixed-path
  replacement, four crash recovery points, and resource-exhaustion cases.
- Rows 30-44 are exactly the 15 lexical request catalog entries from the
  roadmap. The matrix includes explicit SIGINT and corrupt durable state rows
  with exact label/error/termination/scope/delta profiles.
- Release output defaults to `evals/p137/output` and does not overwrite
  final implementation-review inputs.
