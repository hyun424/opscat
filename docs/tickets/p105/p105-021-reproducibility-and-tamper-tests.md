# P105-021 - Reproducibility and Tamper Tests

## Goal

Make release-qualified evidence reproducible and tamper-evident before any
release or P106 unlock claim.

## Tests First

- Add RED tests proving two materializer runs over the same inputs are
  byte-identical for rows, manifests, partitions, coverage summaries, and
  benchmark payloads.
- Add RED tests proving source-record edits change the expected source and
  materialized hashes.
- Add RED tests proving scorer-label edits, row deletion, row duplication, mode
  metadata edits, partition edits, floor weakening, and coverage interval edits
  fail closed.
- Add RED tests proving label tampering fails both when public hashes are left
  unchanged and when public row/artifact hashes are recomputed.
- Add RED tests proving cloned materialized records, duplicated materialized
  hashes, repeated offsets, and repeated source-window-incident keys fail before
  scoring.
- Add RED tests proving tampered artifacts emit `release_qualified=false` and
  `p106_unlocked=false`.

## Implementation Notes

- Hash ledgers must cover enough data to detect row, manifest, partition,
  coverage, and benchmark edits.
- Hashes must not be derived directly from scorer-only labels in public IDs.
- Private label hashes must bind scorer labels to canonical source tuple,
  offset, incident group, and derivation ID.
- Tamper tests should use local temporary artifacts only.

## Acceptance

- Reproducibility is byte-identical for stable inputs.
- Tamper attempts are detected deterministically.
- Tamper acceptance cannot be masked by updating only top-level metadata.
- Tamper acceptance cannot be masked by recomputing public hashes after editing
  private labels.
- Anti-clone checks fail before scoring and cannot be waived by benchmark
  metrics.
- P106 remains locked after any tamper detection.

## Acceptance Commands

Future implementation must make these commands pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_reproducibility.py
```

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
  --p44-mode disabled \
  --output-dir /tmp/opscat-p105-release-qualified-rerun \
  --mode release_qualified
```

## Stop Condition

Stop if any reproducibility run differs unexpectedly, any tampered artifact is
accepted, any label tamper survives public hash recomputation, any clone
inflation survives pre-scoring checks, or any tamper failure can still report
`release_qualified=true` or `p106_unlocked=true`.
