# P105-013 - Deterministic Source-Record Row Generation

## Goal

Generate P105 rows deterministically from raw or materialized P32/P41/P44 source
records with provenance strong enough to reproduce every window, evidence
reference, family, partition, and scorer label.

## Tests First

- Reproducibility test verifies two generator runs over the same materialized
  records produce byte-identical row JSON and partition manifests.
- Provenance test rejects rows missing source system, source path or manifest
  key, source content hash, materialized record hash, record offset or row index,
  source timestamp when available, materialization version, and derivation
  trace.
- Derivation test verifies source-window, evidence-ID, family, failure-mode, and
  label fields come from deterministic transforms over raw/materialized record
  content plus committed metadata, not source ID alone.
- P32 adapter test consumes only local `TrendWindow` replay outputs and
  preserves read-only/no-auth/no-production-mutation boundary counters.
- P41 adapter test consumes only repo-local source cards and committed metadata,
  without downloads, auth, live APIs, action plans, or credential paths.
- P44 adapter test accepts only explicit opt-in public materialization, caps the
  public-source run at 2,000 records, and keeps generated artifacts outside the
  repository unless separately reviewed and redacted as fixtures.
- Family mapping test verifies P32, P41, and P44 rows use the canonical P105
  family mapping table from the roadmap and that unsupported source signals are
  abstained or private-diagnostic only.

## Implementation Notes

- Required row provenance object:
  `source_system`, `source_dataset`, `source_manifest_key`,
  `source_content_hash`, `materialized_record_hash`, `record_offset`,
  `source_timestamp`, `materialization_version`, `window_derivation`,
  `evidence_derivation`, `family_derivation`, and `label_derivation`.
- Canonical source tuple for diversity and provenance:
  `(source_system, source_dataset, source_manifest_key, source_content_hash,
  materialized_record_hash, materialization_version)`. Source IDs, service
  names, or file names alone are not a source tuple.
- Content hashes should be stable over canonicalized raw/materialized record
  bytes. Do not hash scorer labels into public IDs.
- Source-ID-only lineage claims are insufficient and must mark rows
  `unevaluable_provenance_missing`.
- P44 participation is explicit opt-in only. P44 contributes to P105 release
  floors only after rows are materialized, canonicalized, source-hashed,
  family-mapped, redacted, and assigned to `real_derived_shadow`; otherwise it
  has zero denominator contribution.

## Acceptance

- Every P105 release row can be traced to deterministic source record content.
- Every P32/P41/P44 release row has a canonical source tuple and a supported
  family mapping; unsupported mappings do not count toward release floors.
- Public packets expose source provenance only where it cannot leak scorer
  labels or post-incident keys.
- Row generation is local/offline by default and read-only for all adapters.
- Missing provenance keeps `release_qualified=false` and `p106_unlocked=false`.

## Verification

Run source-row generation tests, P32/P41 adapter boundary tests, and the P44
opt-in materialization contract tests when implementation exists.
