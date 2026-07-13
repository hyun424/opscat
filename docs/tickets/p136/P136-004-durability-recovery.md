# P136-004 - Intent, promotion, checkpoint, and recovery

## Scope

Implement index-read-reservation-first, promotion-intent-second, promotion-third,
checkpoint-fourth durable ordering, atomic owner-only writes, fsync semantics,
semantic replay, bounded journals, and explicit durability uncertainty.

## Acceptance

- Crash after index reservation before read and after read before P135 resumes the
  exact cycle/receipt without allocating another receipt.
- Crash after promotion intent and after promotion are deterministic; the latter
  recovers without P135.
- Conflicting or forged state fails closed.
- Pre-replace failure preserves prior bytes; post-replace uncertainty stops.
- Checkpoint binds reserved/consumed receipts, pending partial state, bounded
  canonical entry identities, promotions, counters, and timestamps.
- Budget exhaustion blocks and never deletes evidence.
