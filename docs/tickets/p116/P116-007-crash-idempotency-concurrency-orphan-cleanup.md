# P116-007: crash recovery, idempotency, concurrency, and orphan cleanup

## Goal

Prove the lab can recover from interrupted runs without duplicate actions,
split-brain ownership, corrupted fixtures, or orphan resources.

## Contract

- Persist experiment progress in an append-only receipt log with compare-and-
  set ownership for mutable lab steps.
- Kill the runner before action, during action, during rollback, during reset,
  and during report write.
- Concurrent retries of the same experiment ID must produce one mutable owner
  and deterministic terminal status.
- Replaying a completed experiment is read-only and cannot mutate the fixture.
- Orphan cleanup inventories and removes stale containers, processes, sockets,
  ports, volumes, queue messages, locks, leases, and partial reports.

## Acceptance

Crash and concurrency tests show duplicate lab action count = 0, split-brain
owner count = 0, orphan cleanup success = 1.0, and reset success = 1.0 before
any affected scenario becomes release-counting.
