# P105-017 - Deterministic Local Materializer

## Goal

Build a deterministic local/offline materializer that turns P32/P41/P44 source
records into P105 held-out and real-derived rows with canonical provenance.

## Tests First

- Add RED tests for P32 local replay materialization without live API calls,
  auth, production mutation, or remediation.
- Add RED tests for P41 repo-local source-card materialization without
  downloads, credentials, live APIs, action plans, or credential paths.
- Add RED tests proving P44 is explicit opt-in only, capped at 2,000 records,
  and contributes zero denominator when disabled or unreviewed.
- Add RED tests splitting the P44-disabled negative command from the
  reviewed-local P44 positive command.
- Add RED tests requiring the canonical six-field source tuple:
  `source_system`, `source_dataset`, `source_manifest_key`,
  `source_content_hash`, `materialized_record_hash`, and
  `materialization_version`.
- Add RED tests for deterministic derivation of window IDs, evidence IDs,
  family, failure mode, labels, and row IDs from source content plus committed
  metadata.
- Add RED tests for unique materialized hashes per independent record and at
  most one release row per `(source_tuple, record_offset, source_window_id,
  incident_key, derivation_id)`.

## Implementation Notes

- Generate rows from raw or materialized record bytes, not source ID claims.
- Hash canonical raw/source bytes into `source_content_hash`.
- Hash the redacted row payload before scorer labels are attached into
  `materialized_record_hash`.
- Apply the canonical P32/P41/P44-to-P105 family mapping from the roadmap.
- Unsupported mappings are `unsupported_family` and do not satisfy release
  floors.
- Emit a source-availability preflight manifest before scoring. It must list
  per-family source rows, positives, incidents, source tuples,
  review-redaction status, and local hashes.
- Compare availability floors before scoring. If actual source availability is
  insufficient, the output is locked smoke or diagnostic evidence.

## Acceptance

- Two runs over the same inputs produce byte-identical rows and manifests.
- Every release row has canonical provenance strong enough to reproduce the
  row, partition, coverage, public features, and scorer-only labels.
- P44 remains opt-in and disabled by default.
- Disabled P44 contributes no rows, positives, incidents, source tuples, or
  hashes unless P32/P41 already pass floors without it.
- Reviewed-local P44 contributes only from a reviewed and redacted local
  manifest with stable hashes.
- All materializer authority counters remain false or zero.

## Acceptance Commands

Future implementation must make these commands pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_materializer.py
```

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-mode disabled \
  --output-dir /tmp/opscat-p105-p44-disabled-negative \
  --mode release_qualified \
  --expect-locked
```

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-reviewed-local-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --p44-mode reviewed-local \
  --output-dir /tmp/opscat-p105-release-qualified \
  --mode release_qualified
```

## Stop Condition

Stop if any row lacks the six-field source tuple, source hashes, offsets or row
indexes, deterministic derivation trace, supported family mapping, pre-scoring
availability evidence, anti-clone uniqueness, or zero authority counters.
