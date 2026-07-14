# P137-001 - Contract and schema foundation

## Scope

Implement exact-key, self-hashed P137 config, P136 handoff bundle, evidence
atom, incident, hypothesis, evidence request, classification, ledger, intent,
checkpoint, heartbeat, readiness, termination, and release-evidence schemas.

## Acceptance

- Unknown/missing fields, invalid hashes, invalid timestamps, unsafe paths,
  overlapping state/input roots, and booleans in integer fields fail closed.
- Config requires complete canonical `p137.p136_handoff_bundle.v1` bytes at the
  fixed handoff path; hashes alone are insufficient. Config pins
  `p136_handoff_chain_root_hash`, not each future bundle hash.
- The handoff bundle contains sequence, previous-bundle hash, chain-root hash,
  full P136 config, flattened P136 runtime authority, `now`, qualified P136
  release evidence, final review, checkpoint, canonical entry map, promotion
  map, descriptors, and canonical byte hashes. Byte payloads are canonical
  lowercase hexadecimal exact byte encodings: nonempty even-length `[0-9a-f]`
  strings with no whitespace, prefix, uppercase, or separators. They must
  round-trip through `bytes.fromhex` and `decoded.hex()`, match descriptor
  length and byte hash, and decode into the exact authority byte fields from the
  roadmap without re-emitting P136 canonical JSON bytes.
- Exact forbidden-authority, runtime-activity, evaluator-activity,
  resource-usage, duplicate-count, attempted-request, counter, and score maps
  are defined and validated with no stamped values. The canonical
  `runtime_activity` schema includes measured keys for
  `lease_acquire_count`, `state_read_count`,
  `termination_receipt_write_count`, `ingest_intent_write_count`,
  `evidence_atom_write_count`, `evidence_request_write_count`, and
  `attempted_request_hash_write_count`.
- Named counter-delta profiles are exact-key machine-readable maps, every
  canonical 60-case row references one profile, and byte deltas are
  fixture-derived materialized integers from canonical handoff and promotion
  byte lengths. Profiles are full canonical maps or explicit source-bound
  overrides over the zero full map; legacy profile-only aliases are invalid.
- Closed classifications are exactly `confirmed_incident`,
  `insufficient_evidence`, `benign_anomaly`, and `aborted_fail_closed`.
- Dedicated tests, Ruff, and Mypy pass.
