# P165 Tickets

Dependency: canonical P164 release. Owner surface: durable-shadow classes in
the shared service, P165 fixture, tests, runner, verifier, and `evals/p165`.

1. **P165-001 — Ledger.** Append canonical rows containing cursor, observation
   hash, previous hash, entry hash, status, and observed time. Positive-test
   linkage; negative-test modified row/link.
2. **P165-002 — Checkpoint.** Atomically replace a checkpoint containing last
   cursor and ledger head. Resume exactly once; reject duplicate/out-of-order
   cursor and checkpoint/ledger mismatch.
3. **P165-003 — Liveness.** Classify healthy, precursor, incident, telemetry
   stale (`>30s`), connector unavailable, and deadman expired (`>60s`) without
   executing or approving actions.
4. **P165-004 — Evidence.** Qualify restart after cursor 4 and eight canonical
   cycles. Done when ledger integrity/resume rates are 1.0, duplicate count is
   zero, and all mutation/approval/external counters are zero.
