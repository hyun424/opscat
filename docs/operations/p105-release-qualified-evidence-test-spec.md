# P105 Release-Qualified Evidence Test Spec

Status: planning only. This test spec defines the RED-to-GREEN evidence gate
for future implementation work; it does not claim the tests or materializer
exist yet.

## Test Scope

The test suite must prove that P105 release-qualified evidence is deterministic,
local/offline, source-record based, outcome-neutral, tamper-evident,
P24-comparable, and unable to unlock P106 unless every existing floor and gate
passes. It must also prove that G006 cannot pass by creating ordinal,
partition-position, max-value, or other synthetic signals after seeing private
labels or release floors.

## Test Files

Future implementation must add or update:

- `tests/test_p105_release_qualified_evidence_contract.py`
- `tests/test_p105_release_qualified_materializer.py`
- `tests/test_p105_release_qualified_artifacts.py`
- `tests/test_p105_release_qualified_reproducibility.py`
- `tests/test_p105_release_evidence.py`
- `tests/test_failure_forecast_engine.py`

## RED Expectations

Before implementation, the tests must fail for the intended missing behavior:

- no release-qualified evidence contract validator;
- no deterministic materializer command;
- no locked smoke versus qualified artifact separation;
- no source-availability preflight manifest;
- no private scorer-label answer-key ledger;
- no byte-identical reproducibility manifest;
- no tamper-fail-closed checks;
- no P24 parity check against actual P24 classes for qualified rows;
- no merged coverage and incident-isolation validator for qualified evidence.
- no label-blind P44 sampling proof before NAB label joins or LogHub scorer
  ledger generation;
- no privacy/redaction/license/citation manifest or committed-derived-artifact
  boundary for reviewed-local public artifacts.
- no negative locked tests proving legacy synthetic
  `_write_floor_scale_p44_dataset` rows cannot unlock P106;
- no exact raw-P44-to-reviewed-local command, flat path contract, or
  reviewed-local manifest schema.

## Contract Tests

Required assertions:

- Missing, null, empty, or unknown mode normalizes to
  `smoke_only_missing_mode`.
- `smoke_only` and `smoke_only_missing_mode` always emit
  `release_qualified=false` and `p106_unlocked=false`.
- `release_qualified=true` is impossible unless every supported family passes
  the existing held-out, real-derived, source-diversity, and service-day floors.
- Missing numerator, denominator, source count, incident-group count, coverage
  value, split ID, family ID, or mode field fails closed as
  `unevaluable_missing_denominator`.
- Source availability floors are checked before scoring from a preflight
  manifest with per-family rows, positives, incidents, source tuples,
  review-redaction status, and local hashes.
- Expansion beyond source availability by cloning, duplicated hashes, repeated
  offsets, synthetic padding, or resampling is smoke/diagnostic only.
- Public packets strip scorer labels, incident IDs, incident-group answer keys,
  post-incident values, future timestamps, raw leaked diagnostic payloads, and
  hashes derived directly from those fields.

## Materializer Tests

Required assertions:

- P32 materialization consumes only local P32 replay records and preserves
  no-auth, no-live-API, no-production-mutation, and no-remediation counters.
- P41 materialization consumes only repo-local source cards and committed
  metadata; no downloads, credentials, live APIs, action plans, or credential
  paths are allowed.
- P44 materialization is explicit opt-in only, capped at 2,000 records, and
  contributes zero denominator when disabled or unreviewed.
- Every P32/P41/P44 row includes the canonical six-field source tuple:
  `source_system`, `source_dataset`, `source_manifest_key`,
  `source_content_hash`, `materialized_record_hash`, and
  `materialization_version`.
- Source IDs, provider labels, service names, and file names alone are rejected
  as insufficient provenance.
- Unsupported source signals become `unsupported_family` and cannot satisfy
  supported-family release floors.
- Every independent source record has a unique materialized record hash.
- At most one release row may exist per `(source_tuple, record_offset,
  source_window_id, incident_key, derivation_id)` key.
- A P44-disabled materializer run remains locked unless P32/P41 alone satisfy
  every floor; disabled P44 cannot contribute rows, positives, incident groups,
  source tuples, or hashes.
- A P44-positive materializer run can count P44 only from a reviewed, redacted,
  local manifest with stable local source and materialized hashes.
- The raw-P44-to-reviewed-local command accepts exactly the flat default inputs
  `/private/tmp/opscat-p44-public-artifacts/apache.log`,
  `/private/tmp/opscat-p44-public-artifacts/linux.log`,
  `/private/tmp/opscat-p44-public-artifacts/machine.csv`,
  `/private/tmp/opscat-p44-public-artifacts/ambient.csv`,
  `/private/tmp/opscat-p44-public-artifacts/ec2.csv`, and
  `/private/tmp/opscat-p44-public-artifacts/labels.json`, or an explicit
  `--raw-source-manifest` resolving to the same schema. Nonexistent nested
  paths do not satisfy the contract unless the reviewed raw-source manifest
  names them exactly.
- The reviewed-local P44 manifest includes `raw_sources[]`,
  `sampling_policy`, `reviewed_records[]`, `pre_label_partitions[]`,
  `private_ledger_ref`, privacy/license/citation metadata, and
  `provenance_hashes` with stable hashes for raw sources, reviewed records,
  private ledger, public artifacts, benchmark, and command arguments.
- Reviewed-local rows cannot embed `private_label`, `record_family`,
  `record_partition`, answer-key incident IDs, joined labels, max/peak values,
  release-floor deficits, P24/P105 scores, or gate outcomes in fields that
  satisfy release floors. If present as diagnostic metadata, they contribute no
  rows, positives, incident groups, partitions, source diversity, or coverage.
- P44 sampling is deterministic and label-blind. The sampler may use canonical
  raw bytes, record offset or row index, source manifest key, source timestamp
  when present, and a versioned salt. It must not use NAB official labels,
  LogHub burst labels, private scorer labels, anomaly scores, max observed
  values, P24/P105 scores, partition outcomes, or release-floor deficits.
- NAB `combined_windows.json` labels are joined only after sampling and only
  into the private scorer-label ledger. Sampled rows outside official NAB
  windows are scorer-negative. Missing official windows, missing
  `nab_label_key`, mismatched source hash, or unverifiable label JSON makes the
  affected row `unevaluable_label_join_missing`.
- NAB materialization rejects max-value fallback, peak-value positive creation,
  threshold-created positives, ordinal positive assignment, and synthetic
  anomaly labels.
- LogHub rows may count incidents only through a deterministic scorer ledger
  with parser version, burst predicate, line offsets, source-window boundaries,
  incident group IDs, and source hashes. Every-Nth-row, partition-position,
  ordinal, and floor-driven incident generation fails before scoring.
- Public `public_features`, P24 `TrendWindow` inputs, coverage intervals, and
  private scorer labels all trace to the same sampled source record or sampled
  source window. Cross-record feature/label joins are unevaluable.
- Public `public_features` and P24 `TrendWindow` inputs must come from the same
  raw time window. Missing raw timestamp or missing reconstructable window
  identity emits `unevaluable_missing_raw_window`; the implementation must not
  substitute synthetic broad intervals, floor-sized windows, ordinal windows, or
  unrelated P24 seed windows.
- Source-to-family proxy mapping is explicit and limited: LogHub proxy rows may
  map to `deploy` only through the reviewed burst predicate, and NAB metric
  rows may map to `database` or `queue` only through committed service/metric
  mapping metadata. Unsupported mappings remain `unsupported_family`.
- Legacy synthetic helper data from `_write_floor_scale_p44_dataset` is tested
  only as a negative locked fixture. It must produce
  `release_qualified=false`, `p106_unlocked=false`, and a source-insufficiency
  or synthetic-source stop reason, even if embedded labels, families, or
  partitions would otherwise appear to satisfy floor counts.

## Artifact Tests

Required assertions:

- Locked smoke and qualified artifacts use different file names, manifests,
  hashes, mode fields, and stop conditions.
- Smoke evidence cannot be promoted by changing only mode metadata.
- Qualified artifacts include row manifest, source manifest, partition manifest,
  source-availability preflight manifest, private scorer-label ledger, coverage
  manifest, P24 parity manifest, benchmark payload, and review ledger.
- Qualified artifacts include
  `p105-privacy-redaction-license-citations.json` with source license URLs,
  citation text, reviewer status, redaction decisions, privacy risk notes, and
  redistribution status for every public source.
- Qualified artifacts include `p105-provenance-hashes.json` binding raw source
  hashes, reviewed-local manifest hash, materialized row hashes, private
  ledger hash, public artifact hashes, benchmark hash, and command-line
  arguments. Any missing or mismatched hash locks the release.
- Raw public downloads under `/private/tmp/opscat-p44-public-artifacts` are not
  release artifacts and are not committed by G006. Only reviewed, redacted,
  derived artifacts or fixtures may be committed.
- A missing privacy, license, citation, reviewer, source hash, raw-source path,
  redaction, redistribution, or provenance-hash artifact locks the run before
  benchmark scoring.
- Every manifest has a stable content hash and the benchmark payload references
  those hashes.
- The artifact records every authority counter and all counters are false or
  zero.

## Private Label Ledger Tests

Required assertions:

- Private scorer labels and answer keys live in a ledger that is separate from
  public rows, public manifests, provider packets, and release reports.
- `label_hash` is bound to canonical source tuple, record offset or row index,
  `incident_group_id`, and derivation ID.
- The private ledger is the metrics source of truth for actual positives,
  incident matching, lead-time labels, family labels, and failure-mode labels.
- Editing a label while leaving public hashes unchanged fails closed.
- Editing a label and recomputing public row hashes still fails closed because
  the private label hash ledger no longer matches the reviewed manifest.
- Public artifacts never expose answer-key labels or reversible label hashes.
- The private label ledger records label join phase and source:
  `sampled_before_label_join=true`, `label_join_source=official_nab_windows`
  for NAB, or `label_join_source=deterministic_loghub_error_burst_ledger` for
  LogHub.
- The private label ledger records `reviewed_local_manifest_hash`,
  `pre_label_partition_manifest_hash`, `label_join_completed_after_sampling`,
  and per-record bindings to canonical source tuple, record offset or row
  index, source-window ID, derivation ID, materialized-record hash, and
  pre-label partition ID.
- NAB label records include `nab_label_key`, `labels_json_hash`, official
  window start/end, source timestamp, match status, `label_positive`,
  `incident_group_id`, `label_hash`, and `unevaluable_reason` when no official
  window matches.
- LogHub label records include parser version, burst predicate version, line
  offsets, source-window boundaries, incident group ID, source hash,
  `label_positive`, and `label_hash`.
- The private label ledger rejects labels that are derived from partition ID,
  row ordinal, release-floor deficits, family balancing needs, or max observed
  source values.
- Record-declared partition or family fields are rejected as authoritative
  inputs. Partitions come only from the pre-label partition manifest; family
  comes only from reviewed mapping metadata after source sampling.

## Partition and Coverage Tests

Required assertions:

- `row_id`, `forecast_id`, `source_window_id`, `incident_group_id`, and
  `partition_id` are deterministic over pre-outcome fields plus a versioned
  salt.
- IDs do not encode label positivity, P24/P105 score, useful-lead-time outcome,
  false-alert outcome, safety result, or gate status.
- Partitions are predeclared before scoring and preserve time or deterministic
  sequence ordering.
- Partition assignment for sampled P44 rows is computed from pre-label sampled
  record/window identity. It cannot use joined labels, incident group
  membership, useful lead time, positivity, family-floor deficits, or
  release-gate status.
- An `incident_group_id` appears in exactly one partition.
- Incident groups are created only from official NAB windows or the reviewed
  LogHub error-burst ledger. Synthetic incident groups based on row ordinal,
  partition bucket, or family floor needs fail closed.
- False-alert service-day exposure is the union of coverage intervals per
  `split_id`/`family`/`service`/`source_system` scope.
- Overlapping intervals are merged before seconds are divided by 86400.
- Top-level constants and summed row `covered_seconds` cannot be used as
  false-alert denominators.
- Coverage comes from actual timestamps in raw sources or reviewed-source
  timestamp bounds. Synthetic broad intervals, guessed daily coverage,
  record-count-derived duration, floor-sized coverage, or top-level constants
  cannot satisfy coverage floors.

## P24 Parity Tests

Required assertions:

- P24 baseline rows are produced by actual P24 `RiskSignal` and `RiskForecast`
  behavior from `app.services.proactive_risk_sentinel`.
- P24 and P105 metrics use the same rows, split IDs, families, incident
  matching, service-day scopes, and denominators.
- Simplified fixtures or copied constants cannot satisfy the parity test.
- Brier and ECE improvement rows use `p24_metric - p105_metric > 0.0000`.
- Parity is reconstructable for every row from the exact P24 input bytes or
  canonical input object.
- P24 `TrendWindow` public features are generated from the same sampled source
  record/window as the P105 public feature packet before private labels are
  joined.
- The P24 parity manifest includes `source_window_id`, P24 input hash,
  `RiskSignal` hash, `RiskForecast` hash, and denominator alignment status.
- Missing original P24 input makes the row unevaluable.
- Fallback to unrelated seed windows, fixture defaults, synthetic stand-ins, or
  windows with different source-window identity is rejected.

## Reproducibility and Tamper Tests

Required assertions:

- Two materializer runs over the same inputs produce byte-identical rows,
  manifests, partitions, coverage summaries, and benchmark payloads.
- Reordering input records changes only allowed deterministic ordering outputs
  or is normalized to byte-identical output.
- Changing a source record changes the expected source and materialized hashes.
- Changing raw P44 source bytes, reviewed-local manifest metadata, official NAB
  label windows, LogHub burst predicates, source-to-family mapping metadata,
  privacy/redaction/license/citation manifests, or command arguments changes
  the expected provenance hash and fails closed until re-reviewed.
- Changing a scorer label without updating the hash ledger fails closed.
- Changing a scorer label and recomputing public row or artifact hashes still
  fails closed when the private label ledger hash does not match.
- Removing a row, duplicating a row, changing mode metadata, changing a
  partition, weakening a floor, or editing a coverage interval fails closed.
- Cloning a materialized record, reusing a materialized hash for independent
  records, or emitting multiple release rows for the same source-window-incident
  key fails closed before scoring.
- Any tampered artifact emits `release_qualified=false` and
  `p106_unlocked=false`.

## Review and Verification Tests

Required assertions:

- Independent review status is recorded separately from implementation output.
- Review rejection keeps `release_qualified=false` or blocks final release
  publication until repaired and re-reviewed.
- Full verification evidence includes docs, targeted P105 tests, fast
  verification, release benchmark output, and no known errors.
- Release docs do not claim P106 unlock unless the exact gate payload passes.
- Release-gate evidence records the RED failure command, GREEN command, output
  artifact paths, artifact hashes, reviewed-local P44 manifest hash, benchmark
  hash, and `release_qualified=false` stop reason when floors cannot be met.
- If honest sources cannot meet unchanged per-family floors, the expected GREEN
  state is locked evidence plus an added-source requirement, not fabricated
  labels, lowered gates, or synthetic ordinal/partition incidents.

## Acceptance Commands

These commands are future acceptance commands. They are exact command targets
for implementation tickets, but they are not claimed to pass until the scripts
and tests named above exist.

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_evidence_contract.py \
  tests/test_p105_release_qualified_materializer.py \
  tests/test_p105_release_qualified_artifacts.py \
  tests/test_p105_release_qualified_reproducibility.py
```

P44-disabled negative command:

```bash
uv run --no-sync --extra dev python scripts/materialize_p105_release_evidence.py \
  --p32-replay evals/telemetry/replay/p32_replay_pack.json \
  --p41-sources evals/real_datasets/raw/p41_sources.json \
  --p44-mode disabled \
  --output-dir /tmp/opscat-p105-p44-disabled-negative \
  --mode release_qualified \
  --expect-locked
```

Raw-P44-to-reviewed-local command:

```bash
uv run --no-sync --extra dev python scripts/materialize_p44_reviewed_local.py \
  --apache-log /private/tmp/opscat-p44-public-artifacts/apache.log \
  --linux-log /private/tmp/opscat-p44-public-artifacts/linux.log \
  --machine-csv /private/tmp/opscat-p44-public-artifacts/machine.csv \
  --ambient-csv /private/tmp/opscat-p44-public-artifacts/ambient.csv \
  --ec2-csv /private/tmp/opscat-p44-public-artifacts/ec2.csv \
  --labels-json /private/tmp/opscat-p44-public-artifacts/labels.json \
  --output-dir /tmp/opscat-p105-reviewed-p44 \
  --review-status reviewed-local \
  --expect-source-hashes
```

Reviewed-local P44 positive command:

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

## Stop Conditions

Stop the ticket sequence and keep P106 locked on any failed contract, missing
source-availability preflight, missing denominator, missing provenance field,
missing private label ledger, non-byte-identical reproducibility run, tamper
acceptance, clone inflation, partition leakage, public scorer leakage, P24
parity gap, nonzero authority counter, independent review rejection, or failed
verification command.
