# P105 Release-Qualified Evidence Test Spec

Status: planning only. This test spec defines the RED-to-GREEN evidence gate
for future implementation work; it does not claim the tests or materializer
exist yet.

## Test Scope

The test suite must prove that P105 release-qualified evidence is deterministic,
local/offline, source-record based, outcome-neutral, tamper-evident,
P24-comparable, and unable to unlock P106 unless every existing floor and gate
passes.

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

## Artifact Tests

Required assertions:

- Locked smoke and qualified artifacts use different file names, manifests,
  hashes, mode fields, and stop conditions.
- Smoke evidence cannot be promoted by changing only mode metadata.
- Qualified artifacts include row manifest, source manifest, partition manifest,
  source-availability preflight manifest, private scorer-label ledger, coverage
  manifest, P24 parity manifest, benchmark payload, and review ledger.
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

## Partition and Coverage Tests

Required assertions:

- `row_id`, `forecast_id`, `source_window_id`, `incident_group_id`, and
  `partition_id` are deterministic over pre-outcome fields plus a versioned
  salt.
- IDs do not encode label positivity, P24/P105 score, useful-lead-time outcome,
  false-alert outcome, safety result, or gate status.
- Partitions are predeclared before scoring and preserve time or deterministic
  sequence ordering.
- An `incident_group_id` appears in exactly one partition.
- False-alert service-day exposure is the union of coverage intervals per
  `split_id`/`family`/`service`/`source_system` scope.
- Overlapping intervals are merged before seconds are divided by 86400.
- Top-level constants and summed row `covered_seconds` cannot be used as
  false-alert denominators.

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
