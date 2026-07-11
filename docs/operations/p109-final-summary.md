# P109 Final Summary

P109 now imports and evaluates external operations evidence without gaining
remediation authority.

## Delivered

- Immutable, versioned source manifest and bounded offline-first acquisition.
- Real upstream Baro/RCAEval sample pinned at 570,409 bytes and
  SHA-256 `3eb6169a63f86c5878c277434936e1f4bbbd7f30dcf7f87dc3496bea8cae7f1a`.
- Wide CSV normalization into 41,097 metric observations across 13 services.
- Physically separated candidate evidence and scorer truth; candidate output
  excludes truth metadata, paths, labels, qualification flags, and hashes.
- Diagnosis metrics with explicit numerators, denominators, per-cell results,
  abstention, unsupported claims, and truthless-data unevaluable semantics.
- Clean-room MicroRemed-compatible import with external-execution,
  independent-verifier, signer/public-attestation, and raw health evidence
  requirements; submitted success is ignored.
- Remediation outcome metrics for verified recovery, first-attempt recovery,
  attempts, duration, harmful, unnecessary, no-effect, and unverified results.
- Group/time holdout and exact/near-duplicate contamination protection.
- Actual AST authority scan over the full P109 runtime surface.
- Complete release artifact hash/review binding and fail-closed CLI.

## Evidence

- `p109-release`: 78 tests passed.
- `p108-release`: passed after repairing independently found replay, hash,
  freshness, fixture recomputation, partition, base-version, and rollback
  linkage weaknesses.
- `fast`: compile, Ruff, mypy over 718 files, and the complete pytest regression
  suite passed outside the sandbox where loopback test sockets are permitted.
- Final independent P109 review: **PASS** with no remaining P0/P1/P2.

## Honest current limit

The real CSV has no official root-cause labels, so the current real-source result
is `unevaluable_real_data_missing`; it proves parser/provenance behavior, not
diagnosis accuracy. Real release qualification still requires official labeled
RCA cases and independently signed external remediation results with nonzero
per-system and per-fault-family denominators.
