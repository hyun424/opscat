# P137 Tickets

Execute in dependency order:

1. [P137-001](P137-001-contract-schema.md)
2. [P137-002](P137-002-p136-ingest.md)
3. [P137-003](P137-003-correlation.md)
4. [P137-004](P137-004-hypotheses.md)
5. [P137-005](P137-005-bounded-evidence-requests.md)
6. [P137-006](P137-006-classification-ledger.md)
7. [P137-007](P137-007-recovery-lease-signals-budgets.md)
8. [P137-008](P137-008-canonical-runner-cli.md)
9. [P137-009](P137-009-release-evidence-docs-review.md)
10. [P137-010](P137-010-final-verification.md)

Acceptance gates:

- Do not implement before the ticket's failing tests exist.
- Preserve no-auth, no-credentials, no-network, no-provider-API,
  no-notification, no-action, and no-remediation authority.
- Read only the fixed validated P136 handoff bundle and P137 state; never read
  original provider artifacts.
- Keep exact-key schemas, hash chains, CAS, idempotency, and durable ordering
  validated by tests.
- Use the actual P136 promotion model: `entry_hash` and checkpoint
  `promotion_keys`, with no promotion hash chain. Checkpoint membership is
  `checkpoint.promotion_keys[promotion.entry_hash] == complete canonical
  promotion record`, with embedded `promotion_key` recomputed separately.
- P137-002 owns the P136 fixed-path handoff publisher work: publisher genesis
  sequence/root, root persistence, next sequence allocation, previous-hash
  chaining, checkpoint binding, atomic replace/fsync durability, recovery, and
  idempotent republication. P137 config only pins fixed path and chain root.
- P136 handoff authority byte payloads are canonical lowercase hexadecimal exact
  byte encodings. They must be nonempty even-length `[0-9a-f]` strings with no
  whitespace, prefix, uppercase, or separators, must round-trip through
  `bytes.fromhex` and `decoded.hex()`, and adapt to flattened authority byte
  fields while preserving exact P136 canonical JSON bytes. P137 validates
  `segment_receipt_bytes` against `segment_receipts`; P136 authority validation
  receives only the byte fields it validates plus segment receipt mappings. No
  nested byte wrapper or positional P136 validator calls.
- Delta profiles use only canonical runtime key names and materialize exact full
  maps; stale aliases are invalid.
- Use the lexical 15-entry request catalog order from the roadmap in config,
  matrix rows, tickets, and tests.
- Run targeted verification for each ticket before moving on.
- Release work requires the canonical 60-case matrix, separate plan-readiness and
  final frozen-source implementation reviews, frozen matrix/review consumption
  without regeneration, and exact status
  `p137_local_evidence_triage_qualified`.
