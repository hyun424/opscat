# P136-005 - Lease, bounded loop, signals, and CLI

## Scope

Add one-cycle and foreground bounded-loop commands with exclusive `flock`,
monotonic cadence, finite receipt consumption, failure threshold, graceful
SIGINT/SIGTERM, and termination evidence.

## Acceptance

- Competing in-process and real processes perform no read/promotion.
- Receipt exhaustion and consecutive-failure threshold stop fail closed.
- SIGINT and SIGTERM set a flag and emit termination evidence at a safe boundary.
- Stop reasons, consumed/reserved receipts, counters, and final checkpoint are
  hash-bound.
- Excess clock rollback is rejected while cadence uses a monotonic clock.
- No environment, credential, network, subprocess, or action surface is added.
