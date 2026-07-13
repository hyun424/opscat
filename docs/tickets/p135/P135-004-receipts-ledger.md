# P135-004 - Execution receipts and ledger

## Deliverable

Bind each successful local read and bundle to immutable execution receipts and
a semantically validated ledger.

## Acceptance

- Stable receipt IDs, hash chain, counters, source uniqueness, and bundle links.
- Byte-identical duplicate success-ledger handling without a second success
  receipt or ledger mutation, but with a disclosed validation reread.
- Rehashed counter/bundle/receipt forgeries fail closed.
- Forbidden authority remains exact zero.
- Post-read failures emit denominator-visible failure evidence instead of
  disappearing from evaluation.
- Authority and local observation activity use separate exact counter maps.
