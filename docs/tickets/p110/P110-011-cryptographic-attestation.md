# P110-011 — Cryptographic reviewer and provider-call attestation

## Why

Raw responses, hashes, cache keys, strict replay, and local review make P110
reproducible, but a repository author can still fabricate all local files. A
hard release must not confuse internal consistency with external identity or
proof that a provider call occurred.

## Acceptance criteria

- Configure an out-of-band approved reviewer public-key registry.
- Verify a detached signature over all release artifact hashes and review
  findings; never trust `signature_verified` from review JSON itself.
- Bind provider-issued request identifiers/receipts or a separately signed,
  append-only call ledger to each cache key and raw response hash.
- Rotate/revoke reviewer keys without rewriting historical evidence.
- Add forged-key, revoked-key, replayed-signature, altered-ledger, and missing
  provider-receipt tests.
- Only then may `independent_review_ready` and `release_qualified` become true.

## Current behavior

P110 intentionally fails closed: local review can be internally consistent,
but it cannot satisfy cryptographic reviewer authentication.
