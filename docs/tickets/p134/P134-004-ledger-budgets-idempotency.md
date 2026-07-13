# P134-004 Ledger, Budgets, and Idempotency

Status: complete

Create deterministic self-hashed decision receipts and an ordered ledger with
exact before/after policy counters, budget enforcement, previous-receipt links,
duplicate reuse, and changed-request conflict rejection.

Acceptance: repeated canonical proposals return the original receipt and an
unchanged ledger with only out-of-band duplicate reporting; every counter,
sequence, link, budget transition, and hash is validated; action authority
remains exact zero.
