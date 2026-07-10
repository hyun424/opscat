# P105 Release-Qualified Evidence Plan

Status: planning only. This document does not claim that release-qualified P105
evidence, the materializer, tamper checks, or the qualified artifact already
exist.

## Goal

Produce deterministic local/offline P105 evidence that can be reviewed as a
release-qualified candidate without weakening the existing P105/P106 gates.
The work separates a locked smoke artifact from a qualified artifact, keeps
P106 locked by default, and proves every release claim with reproducible
source-record lineage, P24 parity, merged coverage, incident isolation, and
zero authority.

## Evidence Sources

The materializer must consume only local or explicitly materialized records:

- P32 telemetry replay records from
  `evals/telemetry/replay/p32_replay_pack.json`.
- P41 raw source-card records from `evals/real_datasets/raw/p41_sources.json`.
- P44 public matrix records from
  `evals/real_datasets/external/p44_benchmark_matrix_manifest.json`, only when
  an explicit opt-in materialization run has produced reviewed and redacted
  local records.

No ticket may download public data by default, call external providers by
default, read credentials, use auth, mutate production, execute remediation, or
create P106 action-planning authority.

Before scoring, the materializer must write a source-availability preflight
manifest. The manifest is the gate that proves the qualified run has enough
real source material before any model, rule, or metric can evaluate it. It must
publish, per family and source system:

- available source rows;
- positive labels available to the private scorer;
- incidents and incident groups;
- distinct canonical source tuples;
- review-redaction status;
- local source hashes and materialized record hashes.

If the preflight manifest does not meet the release floors from actual
available records, the run remains `smoke_only` or
`safety_conformance_diagnostic`. Expansion beyond actual availability by
cloning, duplicating, resampling, synthetic padding, or row multiplication is
not release-qualified evidence.

## Required Artifacts

The implementation sequence must produce two distinct evidence artifacts:

| Artifact | Mode | Purpose | P106 effect |
| --- | --- | --- | --- |
| Locked smoke artifact | `smoke_only` or `smoke_only_missing_mode` | Local wiring, formula, leakage, and docs checks over tiny or hand-computed rows | Always `release_qualified=false` and `p106_unlocked=false` |
| Qualified artifact | `release_qualified` | Candidate release evidence generated from deterministic source-record materialization and full gate verification | Can evaluate `p106_unlocked=true` only if every floor, metric, provenance, partition, parity, safety, and review gate passes |

The locked smoke artifact and qualified artifact must be separate files with
separate manifests, hashes, mode fields, and stop conditions. Smoke evidence
must never be promoted by renaming or editing metadata.

## Existing Floors

The plan preserves the exact P105 floors already documented in the roadmap and
model card. For every supported family:

- Held-out floor:
  `held_out_evaluated_window_count >= 30`,
  `held_out_non_abstained_evaluated_forecast_count >= 24`,
  `held_out_actual_positive_count >= 6`,
  `held_out_incident_group_count >= 4`, and
  `held_out_covered_service_seconds / 86400 >= 2.0`.
- Real-derived floor across P32/P41/P44-derived shadow rows:
  `real_derived_evaluated_window_count >= 20`,
  `real_derived_non_abstained_evaluated_forecast_count >= 16`,
  `real_derived_actual_positive_count >= 4`,
  `real_derived_incident_group_count >= 3`, and
  `real_derived_covered_service_seconds / 86400 >= 1.0`.
- Source diversity floor:
  `distinct_source_record_sets >= 3` across materialized P32/P41/P44 inputs,
  and no canonical source tuple may contribute more than `0.60` of a supported
  family's release-qualified real-derived rows.
- Global service-day floor:
  `total_covered_service_seconds / 86400 >= 7.0`.

These floors are credibility floors, not statistical significance claims.
Missing numerator, denominator, source count, incident-group count, coverage
value, split ID, family ID, or mode field keeps `release_qualified=false` and
`p106_unlocked=false`.

## Canonical Provenance

Every P32/P41/P44-derived release row must include the canonical six-field
source tuple:

```text
(source_system, source_dataset, source_manifest_key,
 source_content_hash, materialized_record_hash, materialization_version)
```

Source IDs, service names, provider names, or file names alone are insufficient.
The tuple is both the provenance key and the source-diversity grouping key.

Each row must also publish record offset or row index, source timestamp when
available, deterministic derivation trace, partition ID, coverage intervals,
and hidden scorer labels separated from public packets.

Every independent materialized record must have a unique
`materialized_record_hash`. The materializer may emit at most one release row
for each `(source_tuple, record_offset, source_window_id, incident_key,
derivation_id)` key, where `incident_key` is the private incident ID or
incident-group key used by the scorer ledger. Duplicate rows, cloned records,
or repeated offsets cannot inflate family floors or service-day denominators.

Private scorer labels must be held in a separate answer-key ledger. The ledger
is not a public artifact and is the metrics source of truth for actual
positives, incident IDs, incident groups, lead-time labels, and failure labels.
Each private label record must have a `label_hash` bound to the canonical
source tuple, record offset or row index, `incident_group_id`, and derivation
ID. Public row hashes must not be recomputed from private labels, and private
label hashes must not be exposed in a way that reconstructs answer keys.

## Materializer Rules

The P32/P41/P44 materializer must be deterministic, local/offline by default,
and read-only over source inputs.

- Generate rows from canonical raw or materialized record bytes plus committed
  metadata, never from source ID claims alone.
- Hash canonical source bytes into `source_content_hash`.
- Hash the redacted materialized row payload before scorer labels are attached
  into `materialized_record_hash`.
- Derive source window, evidence IDs, family, failure mode, labels, row IDs,
  incident-group IDs, and partitions from deterministic transforms over
  predeclared inputs.
- Keep P44 explicit opt-in, capped at 2,000 records per public-source run.
- Assign supported real-derived rows only to `real_derived_shadow`.
- Mark unsupported mappings `unsupported_family`; they may support abstention
  or private diagnostics but never satisfy release floors.
- Run source-availability preflight before scoring, then compare floor
  denominators against actual preflight availability rather than scored output.
- Reject clone inflation before scoring by enforcing unique materialized record
  hashes and the one-row-per-source-window-incident key.

The canonical P32/P41/P44-to-P105 family mapping remains the table in
`docs/operations/p105-ticket-roadmap.md`.

## Partition and Coverage Rules

Partitions are predeclared before scoring:

- `train`
- `calibration`
- `held_out_test`
- `real_derived_shadow`
- `safety_conformance_diagnostic`

Partition assignment must use timestamp or deterministic sequence order, source
family, incident-group isolation, and source-record hashes. It must not use
label positivity, P24 score, P105 score, lead-time success, false-alert status,
safety result, or P106 gate status.

Incident groups are isolated across partitions. A single `incident_group_id`
may appear in exactly one partition.

False-alert service-day denominators must be computed from the union of
`coverage_intervals` per `split_id`/`family`/`service`/`source_system` scope.
Overlapping intervals are merged before division by 86400. Row-level
`covered_seconds` is audit evidence only and cannot be summed blindly.

## P24 Parity

The release gate must compare P105 against actual P24 behavior for the same
windows:

- `app.services.proactive_risk_sentinel.RiskSignal`
- `app.services.proactive_risk_sentinel.RiskForecast`

Fixture-only proxies, copied constants, or simplified slope reimplementations
do not satisfy P24 parity. P24 and P105 metrics must share the same row
denominators, split IDs, families, coverage scopes, and incident matching.

P24 parity must be reconstructable per row. The parity manifest must include:

- `source_window_id`;
- canonical P24 input hash;
- `RiskSignal` output hash;
- `RiskForecast` output hash;
- denominator alignment status for P24 and P105 metric rows.

If the original P24 input for a row cannot be reconstructed exactly, the row is
unevaluable for release qualification. The implementation must not fall back to
unrelated seed windows, synthetic stand-ins, fixture defaults, or any window
that does not share the row's source-window identity and input hash.

## Safety and Authority

Every release output must preserve hard-zero authority:

- `auth_enabled=false`
- `production_mutation_enabled=false`
- `action_authority=false`
- `remediation_execution_enabled=false`
- `default_external_model_calls=0`

Safety diagnostic rows are private-harness only. Public and release artifacts
may publish violation metadata, reason codes, and hash-safe references only.
Raw leaked scorer labels, post-incident values, future timestamps, incident
IDs, or raw leaked diagnostic payloads in any public or release artifact make
the affected split `unevaluable_leakage_detected`.

## Ticket Sequence

1. P105-016 creates the release-qualified evidence contract and test spec.
2. P105-017 builds the deterministic local/offline materializer contract.
3. P105-018 locks smoke evidence and prevents smoke promotion.
4. P105-019 generates and validates the qualified artifact contract.
5. P105-020 proves P24 parity, merged coverage, outcome-neutral partitions, and
   incident isolation.
6. P105-021 adds reproducibility and tamper tests.
7. P105-022 closes independent review and full verification.

Each ticket follows RED to GREEN: add or update tests first, observe the
intended RED failure, implement the smallest change, then rerun the exact
acceptance commands until GREEN.

## Acceptance Commands

These are implementation acceptance commands for the future tickets. They are
not claimed to be runnable until the named scripts/tests are added by those
tickets.

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_evidence_contract.py \
  tests/test_p105_release_qualified_materializer.py \
  tests/test_p105_release_qualified_artifacts.py \
  tests/test_p105_release_qualified_reproducibility.py
```

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
  --p44-mode disabled \
  --output-dir /tmp/opscat-p105-release-qualified \
  --mode release_qualified
```

P44-disabled negative command. This command must remain locked unless P32/P41
alone satisfy every release floor; it must not count disabled P44 rows or source
tuples:

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-mode disabled \
  --output-dir /tmp/opscat-p105-p44-disabled-negative \
  --mode release_qualified \
  --expect-locked
```

Reviewed-local P44 positive command. This command may count P44 only from a
reviewed, redacted, local materialization manifest with stable local hashes:

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-reviewed-local-manifest /tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json \
  --p44-mode reviewed-local \
  --output-dir /tmp/opscat-p105-release-qualified \
  --mode release_qualified
```

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark /tmp/opscat-p105-release-qualified/p105-release-qualified-rows.json \
  --output-json /tmp/opscat-p105-release-qualified/p105-release-qualified-benchmark.json
```

```bash
bash scripts/verify.sh --profile docs
bash scripts/verify.sh --profile fast
```

The documentation-only acceptance for this planning commit is:

```bash
git diff --check
bash scripts/verify.sh --profile docs
```

## Stop Conditions

Stop and keep P106 locked if any of the following is true:

- The artifact is `smoke_only`, `smoke_only_missing_mode`, missing mode
  metadata, or tiny-N evidence.
- A supported family misses any held-out or real-derived floor.
- Source diversity has fewer than three canonical source tuples, or one tuple
  exceeds 60% of a supported family's real-derived rows.
- The source-availability preflight manifest is missing, lacks per-family rows,
  positives, incidents, source tuples, review-redaction status, or local hashes,
  or fails floors before scoring.
- Any release floor depends on cloned records, duplicated materialized hashes,
  repeated source offsets, synthetic padding, or expansion beyond actual
  availability.
- Any P32/P41/P44 row lacks the canonical six-field source tuple, content hash,
  materialized record hash, offset/index, or deterministic derivation trace.
- The private scorer-label ledger is missing, exposed publicly, not bound by
  label hashes to tuple, offset, incident group, and derivation, or diverges
  from metric denominators.
- Partition assignment uses outcomes, scores, useful lead time, false-alert
  status, safety results, or gate status.
- An incident group crosses partition boundaries.
- False-alert service days are computed from row sums or top-level constants
  instead of merged coverage intervals.
- P24 parity is not measured against actual P24 `RiskSignal` and
  `RiskForecast`, or any row falls back to unrelated seed windows.
- Any safety authority counter is nonzero.
- Reproducibility runs are not byte-identical, or tamper tests do not fail
  closed.
- Independent review rejects the evidence or full verification fails.
