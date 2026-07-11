# P118-004: signed action-pack verification

## Goal

Verify that every executable P118 operation references a signed, frozen P115
action pack selected by P117 and bound to a local/mock/sandbox fixture target.

## Contract

- Verify P115 action-pack signer, signature, digest, schema version, expiration,
  revocation status, allowed level, fixture target binding, prerequisites,
  contraindications, validation plan, rollback plan, and authority boundary.
- Require exact match between the P117 selected frozen action-pack ID and the
  P115 signed action-pack ID and digest.
- Reject unsigned, stale, revoked, schema-invalid, digest-mismatched, or
  P117/P115-mismatched packs.
- Reject packs containing credentials, auth requirements, production-like
  targets, live connector references, command text, mutable target selectors,
  online policy writes, missing validation, missing rollback, or L4+ levels.
- Record verification result, pack digest, signer receipt, revocation manifest
  hash, expiration check, and authority counter snapshot.

## Acceptance

Valid local/mock/sandbox signed packs verify deterministically. Unsigned, stale,
revoked, mismatched, production-like, auth-bearing, command-bearing, or L4+
packs are accepted 0 times. Exact counters remain zero.

## Stop Rules

Stop if verification trusts P117 prose, accepts invented IDs, skips digest
matching, ignores revocation or expiration, permits production targets,
permits credentials/auth, permits command text, or approves packs without
validation and rollback plans.
