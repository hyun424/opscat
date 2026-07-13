# P136-001 - Config, finite authority, and index-entry contracts

## Scope

Implement exact-key self-hashed P136 config/checkpoint input contracts, bounded
limits, safe path topology, strict index entries, and ordered one-use P134 OA1
index-read receipt validation with durable pre-read reservation.

## Acceptance

- Invalid fields/types/paths/limits/hashes fail closed.
- Runtime requires full canonical P134 contract, review, receipt ledger, and
  ordered receipt bytes, not hashes alone.
- Full chain/membership/distinctness/current-window/proposal/cumulative-budget
  validation occurs before observation.
- One distinct receipt authorizes one deterministic bounded whole-index cycle.
- A self-hashed, atomically written and directory-fsynced
  `p136.index_read_intent.v1` binds checkpoint, cycle, receipt, source, and byte/
  line budgets before any index open/read.
- Retry is legal only from that exact uncommitted reservation; wrong, stale,
  denied, reused, unreserved, or underestimated receipts fail before read.
- Dedicated tests, Ruff, and Mypy pass.
