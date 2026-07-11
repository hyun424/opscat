# P118-003: lease owner and reactive worker loop

## Goal

Define lease acquisition, renewal, expiry, single-owner execution, worker
polling, bounded retries, and split-brain prevention for the reactive worker
loop.

## Contract

- Require a valid owner lease before precheck, action, postcheck, rollback,
  rollback postcheck, terminalization, or report write.
- Store lease acquisition, renewal, expiry, takeover, and release in WAL
  receipts with CAS versions and owner IDs.
- Allow takeover only after lease expiry and successful CAS transition.
- Keep worker polling deterministic, bounded, and local to mock/sandbox queues.
- Record retry attempts, retry reasons, and retry limits.
- Reject concurrent owners, stale renewals, takeover before expiry, worker
  execution without lease receipts, and split-brain execution.
- Preserve exact-zero counters for production mutation, shell/subprocess,
  Kubernetes/cloud/database/network mutation, live connectors, credentials, and
  auth.

## Acceptance

Lease split-brain acceptance is 0, worker execution without ownership is 0,
takeover before expiry is 0, bounded retry receipts are complete, and all
workers preserve local/mock/sandbox-only authority.

## Stop Rules

Stop if two workers can execute the same operation, a worker can act without a
lease, retries are unbounded, lease takeover bypasses CAS, polling touches live
systems, or any non-local authority counter becomes nonzero.
