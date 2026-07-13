# P133 Independent Plan Review

## Implementation clarification

The normalized heartbeat age remains persisted as bounded evidence but is not
part of incident identity. Including a monotonically increasing age in the
fingerprint would emit an `updated` event on every stale poll, defeating the
approved deduplication and reminder contract. Reason, health, state hash, and
runtime-reference hash remain fingerprint-bound; a regression test fixes this
interpretation.

## First review: rejected

The independent critic rejected the first draft because five safety-critical
semantics were not exact: watchdog-vs-readiness scope, the P131 reason mapping,
event timestamp replay after a crash, two-file retention cleanup recovery, and
the authority boundary for `--no-sleep`.

## Corrections applied

- P133 consumes watchdog liveness only; source readiness is deferred to the
  later evidence-investigation phase.
- Every current P131 watchdog reason has an explicit seven-value redaction map:
  one healthy recovery value plus six unhealthy values. Malformed or future
  unknown output becomes generic
  `watchdog_contract_invalid` without copying raw text.
- Event identity excludes time. A crash retry validates and reuses the first
  immutable event's original `occurred_at`, then records the retry check time in
  the cursor.
- Writable paths are pairwise non-overlapping. Retention deletes and fsyncs the
  event before the ack; the only allowed partial state is a validated orphan
  ack, which a later cleanup removes.
- `--no-sleep` is a bounded evaluator-only CLI flag, forbidden with `--forever`
  and in all supervisor manifests.

## Current decision

The second review found one remaining cardinality contradiction: the draft
listed seven normalized values while calling the set six-value. The documents
now state exactly seven values: one healthy recovery value and six unhealthy
values. The final independent review returned **APPROVE** with no concrete
implementation-readiness blocker. Implementation may proceed.
