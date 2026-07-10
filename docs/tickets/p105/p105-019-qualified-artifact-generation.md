# P105-019 - Qualified Artifact Generation

## Goal

Generate the candidate `release_qualified` artifact from deterministic
materialized rows and validate it against floors, gates, provenance, manifests,
and zero-authority counters.

## Tests First

- Add RED tests requiring qualified artifacts to include row, source,
  partition, source-availability preflight, private label, coverage, P24
  parity, benchmark, and review manifests.
- Add RED tests requiring every manifest to have a stable content hash and be
  referenced by the benchmark payload.
- Add RED tests for every existing held-out, real-derived, source-diversity,
  service-day, and P106 gate row.
- Add RED tests proving qualified artifacts fail closed on missing provenance,
  missing denominators, unsupported families, or nonzero authority counters.

## Implementation Notes

- Qualified artifact generation may evaluate `p106_unlocked=true` only after
  all P105 floors and P106 gate rows pass.
- The artifact must not copy scorer-only labels into public packets.
- The artifact must not include raw leaked diagnostic payloads.
- The private label ledger is the metrics source of truth and must be separate
  from public artifacts.

## Acceptance

- The qualified artifact has explicit `mode=release_qualified`.
- Every supported family passes the exact existing P105 floors.
- Source diversity uses canonical six-field source tuples and excludes
  synthetic held-out rows from diversity denominators.
- Pre-scoring source availability passes before metrics are computed.
- Private label hashes are bound to canonical tuple, offset, incident group,
  and derivation ID.
- The artifact records `auth_enabled=false`,
  `production_mutation_enabled=false`, `action_authority=false`,
  `remediation_execution_enabled=false`, and
  `default_external_model_calls=0`.

## Acceptance Commands

Future implementation must make these commands pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_artifacts.py
```

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark /tmp/opscat-p105-release-qualified/p105-release-qualified-rows.json \
  --output-json /tmp/opscat-p105-release-qualified/p105-release-qualified-benchmark.json
```

## Stop Condition

Stop if the candidate artifact lacks a required manifest, lacks stable hashes,
fails pre-scoring availability, fails any floor or P106 gate row, leaks
scorer-only data, has a label-ledger mismatch, or records any authority counter
as enabled.
