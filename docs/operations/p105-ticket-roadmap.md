# OpsCat P105 Ticket Roadmap - Calibrated Failure Forecast Engine

P105 turns P104-qualified evidence plus P24/P25 trend windows into calibrated,
typed forecasts of concrete failure modes. It keeps P24/P25 payload compatibility
for existing callers, but the forecast/action boundary becomes strict:
calibrated forecast output cannot carry an executable prevention plan, and any
legacy `prevention_plan` surfaced through compatibility is marked
`legacy_advisory` until P106 compiles a policy-valid plan.

Boundary: tests-first planning only for this phase; no auth, no production
mutation, no remediation execution, no default external model calls, no scorer
truth leakage, no random future-window leakage, and no use of raw LLM confidence
for execution authority. Optional NVIDIA output is rationale-only and may never
raise execution confidence or unlock P106.

## Evidence Anchors

- P104 produces the shared evidence envelope consumed by P105 and distinguishes
  valid absence from unavailable evidence in `app/services/evidence_gap_investigator.py`.
- P24 defines `TrendWindow`, `RiskSignal`, `RiskForecast`, embedded
  `prevention_plan`, ETA, confidence, and boundary counters in
  `app/services/proactive_risk_sentinel.py`.
- P25 expands the proactive corpus to 120 windows across 42 risk types and
  verifies route, ETA, confidence, capability safety, and no remediation
  execution through `scripts/run_proactive_calibration.py`.
- P32 real telemetry replay turns source-native observability fixtures into
  trend windows through `app/services/telemetry_adapter.py` and
  `app/services/real_telemetry_replay_benchmark.py`.
- P41 raw real-dataset replay scores repo-local source-native files through
  `app/services/raw_real_dataset_replay.py`.
- P104-P108 durable master plan is tracked at
  `docs/operations/p104-p108-proactive-prevention-master-plan.md` so a clean
  clone has the full proactive-prevention context without ignored OMX state.

## G006 Release-Qualified Evidence Planning

G006 is documentation-only planning until RED tests and implementation land. It
does not claim that the deterministic materializer, qualified artifact,
reproducibility checks, or independent review evidence exist.

- Plan:
  `docs/operations/p105-release-qualified-evidence-plan.md`.
- Test spec:
  `docs/operations/p105-release-qualified-evidence-test-spec.md`.
- Plan review:
  `docs/operations/p105-release-qualified-evidence-plan-review.md`.
- Implementation boundary:
  `app/services/failure_forecast_engine.py`.
- Command boundary:
  `scripts/materialize_p105_release_evidence.py` for materialization and
  `scripts/run_failure_forecast_benchmark.py` for scoring.
- Future RED-to-GREEN tests:
  `tests/test_p105_release_qualified_evidence_contract.py`,
  `tests/test_p105_release_qualified_materializer.py`,
  `tests/test_p105_release_qualified_artifacts.py`, and
  `tests/test_p105_release_qualified_reproducibility.py`.
- P44 reviewed-local intake:
  `scripts/materialize_p44_reviewed_local.py` must read either the exact flat
  local raw paths under `/private/tmp/opscat-p44-public-artifacts` or an
  explicit raw-source manifest. It writes
  `/tmp/opscat-p105-reviewed-p44/p44-reviewed-local-manifest.json`.
- Source-expansion amendment:
  `docs/operations/p105-g006-source-expansion-amendment.md`.
- Source-expansion test-spec amendment:
  `docs/operations/p105-g006-source-expansion-test-spec-amendment.md`.
- Qualification-capacity amendment:
  `docs/operations/p105-g006-qualification-capacity-amendment.md`.
- Qualification-capacity test spec:
  `docs/operations/p105-g006-qualification-capacity-test-spec.md`.
- Qualification-capacity plan review:
  `docs/operations/p105-g006-qualification-capacity-plan-review.md`.
- Ticket sequence:
  - `docs/tickets/p105/p105-016-release-qualified-evidence-contract.md`
  - `docs/tickets/p105/p105-017-deterministic-local-materializer.md`
  - `docs/tickets/p105/p105-018-locked-smoke-artifact.md`
  - `docs/tickets/p105/p105-019-qualified-artifact-generation.md`
  - `docs/tickets/p105/p105-020-parity-partition-coverage-isolation.md`
  - `docs/tickets/p105/p105-021-reproducibility-and-tamper-tests.md`
  - `docs/tickets/p105/p105-022-independent-review-full-verification.md`
  - `docs/tickets/p105/p105-023-source-registry-eligibility-plan-review.md`
  - `docs/tickets/p105/p105-024-source-expansion-red-contract-tests.md`
  - `docs/tickets/p105/p105-025-dejavu-a1-and-log-parser-adapters.md`
  - `docs/tickets/p105/p105-026-isolated-queue-harness.md`
  - `docs/tickets/p105/p105-027-isolated-deploy-canary-harness.md`
  - `docs/tickets/p105/p105-028-actual-source-runs-release-benchmark.md`
  - `docs/tickets/p105/p105-029-independent-review-full-verify-p106-gate.md`
  - `docs/tickets/p105/p105-030-qualification-capacity-plan-review.md`
  - `docs/tickets/p105/p105-031-capacity-red-contract-tests.md`
  - `docs/tickets/p105/p105-032-actual-fleet-harnesses.md`
  - `docs/tickets/p105/p105-033-actual-fleet-runs-release-benchmark.md`
  - `docs/tickets/p105/p105-034-capacity-independent-review-gate.md`

## G006 Source-Expansion Amendment

The source-expansion amendment adds one macro sequence after the base P105-RQ
contract: plan review -> RED contract tests -> adapters/harness -> actual runs
-> release benchmark -> independent code and architecture review -> full verify
-> only then P106.

The amendment is documentation-only until implementation lands. It adds these
execution boundaries:

The implemented exact programs later proved mathematically unable to satisfy
the unchanged queue, deploy, and global coverage floors. The second
qualification-capacity amendment therefore preserves the deficient baseline as
evidence and adds a separately reviewed conventional 256-service, one-hour
actual-runtime fleet-soak program for every supported family. P105-030 through P105-034 own that repair;
P106 remains locked until its independent final review passes.

- Reviewed source registry and source eligibility manifest are mandatory before
  scoring. They bind `command_argv`, `created_at`, source hashes, materialized
  hashes, privacy/license/citation status, reviewer status, parser or harness
  version, and eligibility decisions.
- Unsupported-family rows are non-counting for release floors, positives,
  incident groups, source diversity, and coverage.
- DejaVu A1 at `/private/tmp/opscat-dejavu-A1/A1` is the reviewed-local
  database source candidate for explicit `db connection limit` ground truth
  under CC-BY-4.0 metadata review. Because A1 has only seven eligible
  incidents and does not by itself satisfy the unchanged held-out database
  coverage floor, database remains locked unless P105-028 also supplies an
  independently reviewed honest database connection-pool source or isolated
  `p105.database.pool.v1` harness using local SQLite, `sqlite3` connections in
  a bounded `queue.Queue`/`threading.BoundedSemaphore` pool, actual SQL
  insert/select/update operations, fixed partitions, fixed saturation/stall
  schedule, and observed monotonic service-seconds.
- Apache, Hadoop, and Zookeeper rows require actual parser outputs plus
  reviewed deploy/config-regression predicates before counting.
- Queue evidence must come from an isolated local RabbitMQ Docker runtime that
  emits real consumer lag, backlog, and dead-letter telemetry plus a private
  injection ledger. In-memory or schedule-only queue artifacts are RED-only and
  non-counting.
- Deploy evidence must come from actual loopback `ThreadingHTTPServer`
  canary/config regression traffic with measurable error, latency, rollback
  observation, and private injection ledger. Deterministic row materialization
  without HTTP serving is RED-only and non-counting.
- Coverage must come from actual source or harness timestamps only. Fabricated
  four-day coverage, row-count-derived duration, floor-sized intervals,
  accelerated logical clocks, and top-level constants are not
  release-qualified evidence.
- Registry and materializer schema handling is closed: P105-024 owns RED
  adapter/enforcement tests, P105-028 owns explicit schema-adapter CLI parsing
  and fail-closed materialization, and P105-029 owns verifier checks for
  DB-pool arguments, raw runtime attestations, tamper fixtures, and P106 gate
  enforcement.
- Canonical release artifacts exclude volatile runtime IDs, raw monotonic
  nanoseconds, thread identities, container/network IDs, and ephemeral ports.
  Canonical artifacts and manifests also exclude raw attestation paths, raw
  attestation hashes, and any per-run volatile-derived value. Each run writes a
  verifier-owned runtime verification envelope that binds the canonical
  artifact root hash, raw attestation path/hash, and verification result;
  canonical rerun comparison compares only canonical files, while the two run
  envelopes and raw attestations are independently verified and may differ.
- Release-counting runtime kinds are exactly `actual_sqlite_pool`,
  `actual_rabbitmq_docker`, and `actual_threading_http_server`. Source
  telemetry/manifests declare only runtime attestation kind/capability; the
  independent verifier writes the qualification receipt with
  `verified_release_counting=true` only after all checks, and forged source
  fields remain non-counting.
- Existing floors and P106 gate thresholds remain unchanged.

## Outcome

Build a local, deterministic-by-default failure forecast engine that reports:

- concrete failure mode and risk family;
- calibrated probability and probability interval;
- lead-time interval;
- impact scope;
- linked P104 evidence and P24/P25 signal IDs;
- model/rule version and calibration split version;
- abstention reason when evidence, features, coverage, or distribution shift are
  insufficient.

The engine must improve calibration over the deterministic P24 slope/threshold
baseline while preserving the P24/P25 public payload through an adapter.

## Metric Formulas

All benchmark reports must publish counts and denominators, globally and per
family. Unless stated otherwise, abstentions are excluded from forecast-quality
denominators and reported separately.

- `predicted_positive`: non-abstained forecast with calibrated probability at or
  above the family threshold for the evaluated failure family.
- `actual_positive`: labeled failure window for the same family whose incident
  occurs after the forecast timestamp and inside the allowed forecast horizon.
- `true_positive`: predicted positive with matching family and incident in the
  forecast lead-time interval.
- `false_positive`: predicted positive without a matching actual positive in the
  horizon.
- `false_negative`: actual positive with no matching non-abstained predicted
  positive before the incident and inside the maximum forecast horizon.
- `true_negative`: non-abstained evaluated window that is not predicted positive
  and has no actual positive in the horizon.
- `precision = true_positive / (true_positive + false_positive)`. If the
  denominator is zero, report `null` plus the zero denominator.
- `recall = true_positive / (true_positive + false_negative)`. If the
  denominator is zero, report `null` plus the zero denominator.
- `PR-AUC`: area under the precision-recall curve computed by sorting
  non-abstained forecasts by calibrated probability descending, sweeping
  thresholds over unique score values, using actual positives as the positive
  denominator. Report `null` if there are no actual positives.
- `Brier = sum((p_i - y_i)^2) / N`, where `p_i` is calibrated probability,
  `y_i` is 1 for a matching family failure in horizon and 0 otherwise, and `N`
  is the count of non-abstained evaluated forecasts.
- `ECE`: partition non-abstained forecasts into 10 fixed probability bins
  `[0.0,0.1), ... [0.9,1.0]`; for each non-empty bin `b`, compute
  `abs(mean(p_b) - mean(y_b)) * n_b / N`; ECE is the sum over bins. Publish bin
  counts, confidence means, outcome means, and `N`.
- `lead_time_minutes`: `incident_start_timestamp - forecast_timestamp` for true
  positives only. Useful lead time is positive and at least the family minimum
  response window. Report median and p10/p90 over useful true positives.
- `useful_lead_time_rate = useful_true_positive_count / true_positive_count`.
  If the denominator is zero, report `null` plus the zero denominator.
- `false_alerts_per_service_day = false_positive_count / service_days`, where
  `service_days` is computed from the union of coverage intervals for the exact
  evaluated `split_id`/`family`/`service`/`source_system` scope. Overlapping
  intervals for the same service and scope are merged before summing, so
  duplicated rows or replay shards cannot dilute false-alert burden. Publish
  coverage intervals, merged covered seconds, and service-day coverage per
  split, family, service, and source scope.
- `abstention_rate = abstained_window_count / evaluated_window_count`, where
  evaluated windows include every candidate window passed to the forecast engine
  for that split.

Fail-closed denominator rule: if any required numerator, denominator,
service-day coverage value, incident count, family count, or abstention count is
missing from the gate payload, the metric is `unevaluable` and P106 remains
locked. Zero denominators must be reported as `null` metric values with explicit
zero denominators; they may not be coerced to `0.0` or counted as passing.

## P106 Gate Table

P106 can start only when every required row below is `pass=true`. The release
payload must include the formula, numerator, denominator, threshold, split ID,
family or source scope, and pass/unevaluable/fail status for each row.

Gate modes are explicit:

- `smoke_only`: bounded local verification, tiny fixtures, hand-computed metric
  cases, and any run that misses one release-qualification floor. It may prove
  wiring and formulas, but it can never unlock P106.
- `release_qualified`: the only mode eligible to evaluate `p106_unlocked=true`.
  It must pass every P106 gate row below and every release-hardening floor in
  this roadmap. Missing mode metadata is normalized to
  `smoke_only_missing_mode`.

Mode normalization is deterministic and fail closed: any missing, null, empty,
or unknown mode normalizes to `smoke_only_missing_mode`, which is a `smoke_only`
substatus with `release_qualified=false`, `p106_unlocked=false`, and no P106
gate-row pass credit. The current committed P105 fixture files are smoke
fixtures only: `p105_curated_synthetic_rows.json` has no mode metadata and 12
rows, `p105_real_derived_shadow_rows.json` has no mode metadata and 4 rows, and
`p105_release_benchmark_rows.json` has no mode metadata and 21 rows. Until a
future implementation emits explicit `mode=release_qualified` and passes every
floor below, these committed fixtures normalize to `smoke_only_missing_mode`.

The release-hardening floors are anti-tiny-N credibility checks, not statistical
significance claims. They are sized to be meaningful but achievable from the P44
max-2,000-record public-source path plus committed P32/P41 materialized replay
fixtures. If a supported family cannot meet them, P105 must either keep the
release in `smoke_only` or withdraw that family from `supported_families` before
claiming release qualification.

| Gate row | Scope | Formula and denominator | Required threshold |
| --- | --- | --- | --- |
| Held-out Brier improvement | Global and each supported family with `actual_positive_count > 0` | `brier_improvement = p24_brier - p105_brier`, where each Brier is `sum((p_i - y_i)^2) / non_abstained_evaluated_forecast_count` on the same held-out rows | `brier_improvement > 0.0000` |
| Held-out ECE improvement | Global and each supported family with `actual_positive_count > 0` | `ece_improvement = p24_ece - p105_ece`, where each ECE uses the 10 fixed bins and `N = non_abstained_evaluated_forecast_count` | `ece_improvement > 0.0000` |
| Useful lead-time rate | Each supported family with `actual_positive_count > 0` | `useful_true_positive_count / true_positive_count`; useful means `lead_time_minutes >= family_min_response_minutes` and `lead_time_minutes > 0` | `>= 0.80` per supported family |
| Zero-positive family semantics | Each supported family with `actual_positive_count = 0` | No rate is computed because `true_positive_count = 0`; publish `unevaluable_zero_positive=true` | P106 locked unless the family is explicitly removed from `supported_families` before release |
| False alerts per service-day | Global and each supported family | `false_positive_count / service_days`, where `service_days = covered_service_seconds / 86400` for the evaluated split | `<= 0.25` globally and `<= 0.50` per family |
| Abstention ceiling | Global and each supported family | `abstained_window_count / evaluated_window_count`; evaluated windows include non-abstained forecasts plus abstentions | `<= 0.20` globally and `<= 0.30` per family |
| Real-derived useful lead-time transfer | Each supported family present in P32 or P41 shadow replay with `actual_positive_count > 0` | `held_out_useful_lead_time_rate - real_derived_useful_lead_time_rate`, where each rate uses `useful_true_positive_count / true_positive_count` for that family and split | `<= 0.10` directional drop; real-derived rate must also be `>= 0.80` |
| Real-derived false-alert transfer | Each supported family present in P32 or P41 shadow replay | `real_derived_false_alerts_per_service_day - held_out_false_alerts_per_service_day` | `<= 0.10` absolute increase and still within the false-alert threshold |
| Safety boundary | Whole release | Boundary counters and release metadata | no auth, no production mutation, no remediation execution, no executable action plan, no default external model calls |

## Release-Hardening Floors

These floors preserve the existing P106 thresholds while preventing a tiny
fixture from making the gate look credible.

For every family in `supported_families`:

- Held-out coverage floor:
  `held_out_evaluated_window_count >= 30`,
  `held_out_non_abstained_evaluated_forecast_count >= 24`,
  `held_out_actual_positive_count >= 6`,
  `held_out_incident_group_count >= 4`, and
  `held_out_covered_service_seconds / 86400 >= 2.0`.
- Real-derived coverage floor across P32/P41/P44-derived shadow rows:
  `real_derived_evaluated_window_count >= 20`,
  `real_derived_non_abstained_evaluated_forecast_count >= 16`,
  `real_derived_actual_positive_count >= 4`,
  `real_derived_incident_group_count >= 3`, and
  `real_derived_covered_service_seconds / 86400 >= 1.0`.
- Source diversity floor:
  `distinct_source_record_sets >= 3` across P32/P41/P44 materialized inputs for
  the release, and no single canonical source tuple may contribute more than
  `0.60` of a supported family's release-qualified real-derived rows:
  `max_source_tuple_family_row_count /
  family_release_qualified_real_derived_row_count <= 0.60`. Synthetic held-out
  rows are excluded from both the numerator and denominator of this diversity
  fraction. P32/P41/P44 rows count only when they are materialized, canonicalized,
  source-hashed, redacted, assigned to `real_derived_shadow`, and otherwise
  release-qualified.
- Service-day floor:
  global held-out plus real-derived coverage must satisfy
  `total_covered_service_seconds / 86400 >= 7.0`.

Fail-closed formulas:

- `release_qualified = true` only if every supported family passes all held-out
  and real-derived floors, every source-diversity floor passes, every P106 gate
  row is `pass=true`, and every safety boundary counter is zero.
- If any numerator, denominator, source count, incident-group count,
  `covered_service_seconds`, split ID, family ID, or mode field is missing,
  then `release_qualified=false`, `p106_unlocked=false`, and
  `qualification_status="unevaluable_missing_denominator"`.
- If a run is `smoke_only`, then `p106_unlocked=false` even when formulas pass
  on the tiny fixture.

Supported-family rule: every family declared in the P105 model/rule card as
supported must pass the per-family rows above. Families that cannot produce a
positive held-out or real-derived denominator are not silently averaged into the
global score; they are `unevaluable` and keep P106 locked until support is
withdrawn or fixture coverage is added.

Real-derived useful-lead-time transfer is directional. It allows real-derived
shadow replay to match or exceed held-out useful-lead-time rate, and blocks only
when the held-out rate exceeds the real-derived rate by more than `0.10`. The
gate must compute `held_out_useful_lead_time_rate -
real_derived_useful_lead_time_rate <= 0.10`; implementations must not use an
order-insensitive comparison. Both rates use the same per-family denominator,
`true_positive_count`, and the same useful numerator,
`useful_true_positive_count`. Missing numerator or denominator values, zero
`true_positive_count`, missing `actual_positive_count`, or missing split/source
identity make the row `unevaluable` and keep P106 locked.

## Fixture and Label Contract

P105 fixture rows must use this deterministic schema before any implementation
work begins:

- `row_id`: stable unique row key.
- `source_window_id`: P24/P25/P32 trend window ID or P41 source-card-derived
  window ID.
- `family`: supported forecast family.
- `failure_mode`: concrete failure label inside the family.
- `service`: redacted service identifier.
- `metric`: metric or signal name.
- `forecast_timestamp`: ISO-8601 timestamp or deterministic sequence timestamp
  when source timestamps are unavailable.
- `window_start_timestamp` and `window_end_timestamp`: ISO-8601 timestamps for
  the input window; if sequence-only, publish `sequence_start` and
  `sequence_end` instead.
- `label_incident_id`: scorer-only incident ID.
- `label_incident_start_timestamp`: scorer-only incident start timestamp.
- `label_family`, `label_failure_mode`, and `label_positive`: scorer-only
  answer fields.
- `lead_time_label_minutes`: scorer-only derived value used only after scoring.
- `incident_group_id`: scorer-only split isolation key.
- `public_features`: feature payload visible to training/forecasting.
- `scorer_labels`: hidden answer-key object containing all label fields.
- `source_record_ref`: structured provenance object for raw/materialized
  records, including source system (`p32`, `p41`, or `p44`), source path or
  manifest key, source content hash, materialized record hash, record offset or
  row index, source timestamp when available, materialization version, and the
  deterministic derivation trace for source window, evidence IDs, family, and
  label fields.
- `coverage_intervals`: one or more `[start_timestamp, end_timestamp)` service
  coverage intervals for this row and source scope.
- `covered_seconds`: row-level coverage seconds retained for row audit only;
  false-alert/service-day scoring must use the union of `coverage_intervals` per
  split/family/service/source scope instead of summing this value blindly.
- `partition_id`: predeclared partition assignment, chosen before scoring and
  independent of outcome.

Public packets for training, calibration, provider rationale, and forecast
rendering must strip `label_incident_id`, `label_incident_start_timestamp`,
`label_family`, `label_failure_mode`, `label_positive`,
`lead_time_label_minutes`, `incident_group_id`, post-incident values, and any
other `scorer_labels` member. If a public packet contains one of those fields,
the split and benchmark fail closed.

## Incident Matching Semantics

Scoring uses deterministic one-to-one matching per family and split:

1. Sort predicted positives by `forecast_timestamp` ascending, then calibrated
   probability descending, then `forecast_id` ascending.
2. For each prediction, consider only unmatched actual incidents with the same
   family whose `label_incident_start_timestamp` is after the forecast timestamp
   and inside the maximum forecast horizon.
3. Pick the incident with the earliest valid start timestamp; break remaining
   ties by `label_incident_id` ascending.
4. Mark that pair as one true positive. A second alert for the same already
   matched incident is a duplicate alert and counts as a false positive for
   false-alert burden.
5. An actual incident with no matched non-abstained forecast is one false
   negative. Abstentions before that incident do not match it and therefore do
   not prevent the false negative.
6. Abstained rows count only in abstention denominators. They are never true
   positives, false positives, or true negatives.

## P32/P41 Adapter Responsibilities

P32 adapter responsibilities for P105 are limited to read-only transformation
of local real telemetry replay outputs into P105 shadow rows: consume P32
`TrendWindow`-shaped replay windows, preserve source/window IDs, map
`risk_type` to P105 `family`/`failure_mode`, carry covered-service seconds,
emit public feature fields, and keep P32 boundary counters proving no live API
calls, auth, production mutation, or remediation execution.

P41 adapter responsibilities for P105 are limited to read-only transformation
of repo-local raw real-dataset replay source cards into P105 shadow rows:
consume source ID, family, labels seen, expected labels/root cause/route, parsed
record count, and prediction evidence; derive label windows only from committed
source-card metadata; strip scorer-only labels from public packets; and preserve
P41 boundary counters proving no downloads, live API calls, auth, production
mutation, or remediation execution. Neither adapter may create an action plan,
policy handoff, credential path, or production mutation path.

P44 participation is optional, explicit opt-in, and never assumed from the
presence of a public-source path. P44 adapter responsibilities for P105 are
limited to read-only transformation of explicitly materialized public-source
records, capped at 2,000 records per opt-in public run. P44 contributes to
release floors only after materialized rows are canonicalized, source-hashed,
family-mapped, redacted, and assigned to `real_derived_shadow`; otherwise P44
has zero denominator contribution and cannot be counted for source diversity.
The adapter must generate rows from raw/materialized record content and hashes,
not from source ID claims alone. Public downloads remain explicit opt-in and
generated artifacts remain outside the repository unless converted into
reviewed, redacted fixtures.

The exact flat P44 raw-source inputs for the reviewed-local handoff are:

- `/private/tmp/opscat-p44-public-artifacts/apache.log`
- `/private/tmp/opscat-p44-public-artifacts/linux.log`
- `/private/tmp/opscat-p44-public-artifacts/machine.csv`
- `/private/tmp/opscat-p44-public-artifacts/ambient.csv`
- `/private/tmp/opscat-p44-public-artifacts/ec2.csv`
- `/private/tmp/opscat-p44-public-artifacts/labels.json`

The exact reviewed-local command is:

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

Manifest-driven intake is allowed only with
`--raw-source-manifest /path/to/reviewed-p44-raw-source-manifest.json`; the
manifest must list exact local paths, source keys, source hashes, license and
citation metadata, privacy review status, reviewer identity, and timestamp
bounds. Nonexistent nested paths are not part of the P105 handoff unless that
reviewed manifest names them exactly.

The reviewed-local manifest must contain `raw_sources[]`, `sampling_policy`,
`reviewed_records[]`, `pre_label_partitions[]`, `private_ledger_ref`, and
`provenance_hashes`. Required source fields include `source_key`,
`source_system`, `source_dataset`, `source_manifest_key`, `local_path`,
`source_content_hash`, `record_count`, `timestamp_min`, `timestamp_max`,
`license_url`, `citation_text`, `redistribution_status`,
`privacy_review_status`, `redaction_decisions`, `reviewer_id`, and
`reviewed_at`. Required record fields include `reviewed_record_id`,
`record_offset` or `row_index`, `source_timestamp`, `source_window_id`,
`window_start_timestamp`, `window_end_timestamp`, `public_feature_hash`,
`p24_input_hash`, `materialized_record_hash`, `coverage_interval_ids`, and
`pre_label_partition_id`.

The reviewed-local manifest cannot use embedded `private_label`,
`record_family`, `record_partition`, answer-key incident IDs, max/peak values,
release-floor deficits, P24/P105 scores, or gate outcomes to satisfy release
floors. Family assignment comes from reviewed mapping metadata. Partition
assignment comes only from the pre-label partition manifest. Private labels
come only from the separate scorer-label ledger after sampling and pre-label
partitioning.

P44 sampling is label-blind. Reviewed-local P44 rows are sampled
deterministically from canonical raw public source bytes, record offset or row
index, source manifest key, source timestamp when present, and a versioned
salt before private labels, official label files, incident groups, P24/P105
scores, release floors, or partitions are read. NAB `combined_windows.json`
official label windows join only after sampling and only in the private scorer
ledger; missing official windows or missing `nab_label_key` makes the affected
row unevaluable. NAB max-value fallback, peak-value positives, threshold-created
positives, ordinal positives, and synthetic anomaly labels are forbidden.

Public feature packets and P24 `TrendWindow` inputs must be reconstructed from
the same raw time window before private labels join. Missing raw timestamps,
missing window identity, synthetic broad intervals, record-count-derived
coverage, floor-sized coverage, ordinal windows, or unrelated P24 seed windows
make the row unevaluable.

LogHub public logs may count incidents only through a deterministic private
scorer ledger with a reviewed parser version, error-burst predicate, line
offsets, source-window boundaries, incident group IDs, and source hashes.
Every-Nth-row, partition-position, ordinal, or floor-driven incidents are not
release-qualified evidence.

Legacy synthetic helper data such as `_write_floor_scale_p44_dataset` is a
negative locked fixture only. It can prove that synthetic rows remain locked,
but it cannot be converted into an unlock test and cannot count embedded
private labels, record families, record partitions, positives, incident groups,
source diversity, or coverage.

Canonical source tuple: every P32/P41/P44-derived row must publish
`source_tuple=(source_system, source_dataset, source_manifest_key,
source_content_hash, materialized_record_hash, materialization_version)`.
`source_dataset` is the replay dataset or public-source collection name, not a
human-readable provider label. `source_manifest_key` is the stable manifest path
or logical key. `source_content_hash` is over canonical raw/source bytes.
`materialized_record_hash` is over the canonical row payload after redaction but
before scorer labels are attached. Diversity denominators group rows by this
tuple; source IDs, service names, or file names alone are insufficient.

P32/P41/P44-to-P105 family mapping is canonical:

| Source | Source signal | P105 family | Participation |
| --- | --- | --- | --- |
| P32 | `connection_pool_saturation`, `slow_query_risk`, `lock_wait_risk`, `db_max_connections_risk`, `replica_lag_read_risk`, `wal_growth_risk`, `vacuum_lag_risk`, `index_bloat_risk` | `database` | Real-derived shadow if local replay output is materialized and source-hashed |
| P32 | `queue_sla_breach`, `consumer_lag_risk`, `dead_letter_growth_risk`, `webhook_lag_risk` | `queue` | Real-derived shadow if local replay output is materialized and source-hashed |
| P32 | `canary_regression_risk`, `feature_flag_degradation_risk`, `schema_drift_risk` | `deploy` | Real-derived shadow if local replay output is materialized and source-hashed |
| P41 | source-card `family=loghub` or `aiops` with `expected_root_cause=deploy_regression` or deploy/config labels | `deploy` | Real-derived shadow from repo-local source cards only |
| P41 | source-card `family=nab` or `aiops` with metric anomaly, saturation, lag, or capacity labels | `database` or `queue` by service/metric manifest mapping | Real-derived shadow from repo-local source cards only |
| P44 | LogHub `loghub_raw` sampled raw log windows with reviewed error-burst scorer ledger | `deploy` proxy only when the reviewed burst predicate represents deploy/config regression; otherwise `unsupported_family` | Real-derived shadow only after redacted fixture review and private ledger join |
| P44 | NAB `nab_csv` sampled metric windows with official `combined_windows.json` label join after sampling | `database` or `queue` proxy only through committed service/metric mapping metadata; otherwise `unsupported_family` | Real-derived shadow only after redacted fixture review and private ledger join |

Any source signal outside this table is `unsupported_family` until a future
planning change adds an explicit mapping. Unsupported rows may be used only for
private safety diagnostics or abstention checks; they do not satisfy supported
family release floors.

P44-to-P105 mappings are source-to-family proxies with explicit limitations,
not proof of true production database, queue, or deploy failures. Release
artifacts must publish `family_proxy_mapping`, `proxy_limitations`,
`unsupported_family_count`, and mapping review status. Existing per-family
floors are unchanged; if honest sampled public sources cannot satisfy them,
G006 stays locked and adds reviewed sources instead of fabricating labels or
lowering gates.

Source insufficiency is a terminal locked result for the current reviewed input
set. If actual reviewed sources cannot meet unchanged floors from real
timestamps, reviewed labels, and source hashes, the implementation records the
stop reason and leaves `release_qualified=false` and `p106_unlocked=false`.
Adding more public or local source material is a separate reviewed input change
with new privacy, license, citation, reviewer, and provenance-hash artifacts.

## Partition and Diagnostic Semantics

Partitions are predeclared before scoring: `train`, `calibration`,
`held_out_test`, `real_derived_shadow`, and
`safety_conformance_diagnostic`. Partition assignment uses timestamp or
deterministic sequence order, source family, incident-group isolation, and
source-record hashes. It must not use model outcomes, P105 scores, P24 scores,
lead-time success, false-alert status, or safety results.

Outcome-neutral IDs are required. `row_id`, `forecast_id`, `source_window_id`,
`incident_group_id`, and `partition_id` must be deterministic hashes over
pre-outcome fields plus a versioned salt. They must not encode label positivity,
failure outcome, safety pass/fail, useful lead time, or gate status.

Safety-conformance diagnostic rows exist only in a private test harness to prove
boundary handling for expected invalid preconditions such as malformed public
packets, unsupported families, intentionally leaked scorer-label sentinels,
post-incident values, mutation authority, or external-call attempts. Expected
precondition violations in this private partition are excluded from performance
metrics, and public/release artifacts may publish only violation metadata,
reason codes, and hash-safe references that cannot reconstruct scorer labels,
incident IDs, post-incident values, or future timestamps. Any unexpected
successful forecast, unexpected action-shaped output, credential/auth path,
production mutation, default external call, or nonzero safety counter fails the
safety gate. Valid and evaluable rows from supported families may never be
moved into `safety_conformance_diagnostic` or excluded from performance to
improve scores.

Post-incident key leakage fails closed. If a public training, calibration,
forecast, rationale, release packet, release evidence file, model card, or
verification artifact contains post-incident values, scorer-only labels,
incident IDs, incident-group answer keys, lead-time labels, future timestamps,
raw leaked diagnostic payloads, or hashes derived directly from those fields,
the affected split is `unevaluable_leakage_detected`,
`release_qualified=false`, and `p106_unlocked=false`. Intentional leak fixtures
are allowed only inside the private safety harness and must never be copied into
public or release artifacts.

## Tickets

### P105-000 Forecast/action split and P24 compatibility adapter

Introduce the strict forecast/action split and the versioned adapter that keeps
P24/P25 output shape stable while marking legacy prevention output advisory.

Acceptance:
- Calibrated forecast objects contain no executable action list, no action
  route, and no policy handoff field.
- P24/P25 compatibility output still contains `prevention_plan`, but it is
  labeled in the compatibility payload as
  `compatibility.legacy_advisory=true`, includes
  `prevention_plan.legacy_advisory=true`, keeps every nested action
  `action_execution_enabled=false`, and sets
  `compatibility.p106_required_for_execution=true`.
- Existing P24/P25 smoke expectations remain expressible through the adapter.

### P105-001 Typed forecast schema

Define the typed schema for calibrated forecasts, forecast inputs, abstentions,
and benchmark rows.

Acceptance:
- Schema includes forecast ID, source window ID, episode/decision IDs from P104
  when present, family, concrete failure mode, probability, probability interval,
  lead-time interval, impact scope, evidence IDs, feature coverage, split ID,
  model/rule version, calibration version, and abstention reason.
- JSON round trips preserve all fields and reject missing IDs, probabilities
  outside `[0, 1]`, invalid intervals, duplicate evidence IDs, and unknown
  abstention reasons.
- Public rendering strips scorer-only labels and future outcome fields.

### P105-002 Leakage-resistant time-ordered split

Create the train/calibration/test fixture split contract before model code.

Acceptance:
- Splits are ordered by timestamp or deterministic sequence ID: train precedes
  calibration, calibration precedes test, and all windows from the same incident
  group stay in one split.
- Tests fail if a future point, later incident sibling, scorer outcome, or
  post-incident label is visible to an earlier split.
- Split metadata records family coverage, service-day coverage, incident group
  counts, and zero overlap hashes.

### P105-003 Deterministic P24 baseline

Freeze the current P24 slope/threshold logic as the baseline comparator.

Acceptance:
- Baseline reproduces P24 `RiskSignal.from_window` ETA/confidence and
  `ProactiveRiskSentinel._forecast` routing behavior for the P25 corpus.
- Baseline reports the same metrics as the calibrated engine, including Brier,
  ECE, lead time, false alerts/service-day, and abstention rate.
- Baseline remains deterministic, local/mock, and network-free.

### P105-004 Multi-signal feature builder

Build feature extraction over P24/P25 windows plus P104-qualified evidence.

Acceptance:
- Features cover trend slope, threshold distance, baseline ratio, seasonality
  proxy, deploy/config change proximity, saturation pressure, volatility,
  evidence sufficiency state, valid absence vs unavailable evidence, and
  cross-service correlation.
- Feature builder emits per-feature provenance and missingness flags.
- Missing critical features never silently impute a confident forecast.

### P105-005 Calibration and uncertainty

Add probability calibration and uncertainty intervals without using LLM
confidence as a scoring input.

Acceptance:
- Calibration is fit only on the calibration split after training/baseline score
  generation and before held-out test evaluation.
- Output includes calibrated probability, lower/upper interval, calibration
  method/version, and bin-level reliability data.
- Brier and ECE improve over the deterministic P24 baseline on the held-out
  time-ordered test split, or the release gate fails.

### P105-006 Missing-feature and distribution-shift abstention

Define conservative abstention for low coverage, missing critical features, and
distribution shift.

Acceptance:
- Abstention reasons include `missing_critical_feature`,
  `insufficient_p104_evidence`, `telemetry_unavailable`,
  `distribution_shift`, `unsupported_family`, `low_service_day_coverage`, and
  `invalid_split`.
- Shift checks compare held-out feature distributions against train/calibration
  reference ranges and publish drift statistics.
- Abstained cases cannot unlock P106 and are included in abstention-rate
  denominators.

### P105-007 Optional NVIDIA rationale guard

Allow opt-in NVIDIA rationale text only as an explanation aid.

Acceptance:
- Default verification performs zero external model calls.
- Provider packets exclude scorer truth, future labels, action authority, and
  production credentials.
- NVIDIA rationale cannot change calibrated probability, threshold, route,
  abstention, or P106 gate status.

### P105-008 Per-family lead-time and false-alert benchmark

Implement the benchmark contract with exact denominators and per-family tables.

Acceptance:
- Reports include precision, recall, PR-AUC, Brier, ECE, median useful lead
  time, p10/p90 useful lead time, false alerts/service-day, and abstention rate.
- Every metric publishes numerator, denominator, split ID, family, severity, and
  threshold.
- At least 80% of curated true-positive forecasts have useful positive lead time
  for every supported family with positive labels; zero-positive supported
  families are `unevaluable`, not passing.

### P105-009 Real-derived shadow transfer gate

Evaluate shadow forecasting over source-native and real-derived replay surfaces.

Acceptance:
- P32 real telemetry replay trend windows and P41 raw real-dataset source cards
  are used as read-only shadow inputs with no live API calls and no remediation.
- Transfer report compares held-out synthetic performance to real-derived shadow
  performance by family and source.
- P106 remains blocked unless held-out calibration thresholds and real-derived
  useful lead-time/false-alert thresholds pass.

### P105-010 Model card and release verification

Document the model/rule card, boundary, validation evidence, and release gate.

Acceptance:
- Model card states data sources, split IDs, feature families, calibration
  method, thresholds, abstention policy, known limitations, and non-goals.
- Release evidence records P24 baseline metrics, calibrated metrics, shadow
  transfer metrics, safety counters, and P106 gate status.
- `scripts/verify.sh` integration remains local/offline by default.

### P105-011 Release integration and P106 gate lock

Wire P105 evidence into docs/tests/release checks while keeping P106 locked
unless thresholds pass.

Acceptance:
- P105 release tests assert that no `docs/operations/p106-*` implementation
  summary claims unlock before P105 held-out and real-derived transfer gates pass.
- Gate payload exposes `p106_unlocked=false` by default and only becomes true
  when held-out Brier/ECE, useful lead-time, false-alert, and transfer thresholds
  pass.
- Gate payload uses the P106 gate table exactly, including fail-closed missing
  denominators, per-supported-family `>= 0.80` useful lead time, false
  alerts/service-day, abstention ceilings, and directional real-derived transfer
  tolerance.
- If the gate fails, the release summary explicitly stops at shadow forecasting.

### P105-012 Release qualification floors and mode semantics

Add explicit `smoke_only` versus `release_qualified` run modes plus
anti-tiny-N floors for held-out and real-derived evidence.

Acceptance:
- Smoke, tiny-N, hand-computed, and fixture-only wiring runs always emit
  `mode=smoke_only`, `release_qualified=false`, and `p106_unlocked=false`.
- `release_qualified=true` requires every supported family to pass the held-out
  floors (`evaluated >= 30`, `non_abstained >= 24`, `actual_positive >= 6`,
  `incident_group_count >= 4`, `service_days >= 2.0`) and the real-derived
  floors (`evaluated >= 20`, `non_abstained >= 16`, `actual_positive >= 4`,
  `incident_group_count >= 3`, `service_days >= 1.0`).
- Release evidence proves at least three distinct canonical source tuples
  across P32/P41/P44 materialized real-derived inputs, no single source tuple
  contributes more than 60% of any supported family's release-qualified
  real-derived rows, synthetic held-out rows are excluded from the source
  diversity denominator, and global service coverage is at least seven
  service-days.
- Missing floor denominators or mode metadata fail closed as
  `smoke_only_missing_mode` plus `unevaluable_missing_denominator`.

### P105-013 Deterministic source-record row generation

Build the P32/P41/P44 row-generation contract from raw/materialized source
records with content hashes and derivation metadata.

Acceptance:
- Every row records source system, source path or manifest key, source content
  hash, materialized record hash, record offset or row index, source timestamp
  when available, materialization version, source-window derivation,
  evidence-ID derivation, family derivation, and label derivation.
- Every P32/P41/P44 row records the canonical source tuple and uses the
  P32/P41/P44-to-P105 family mapping table above; unsupported source signals are
  abstained or private-diagnostic only and never count toward release floors.
- Re-running the generator from the same raw/materialized inputs produces
  byte-identical rows and partition manifests.
- Source-ID-only assertions are insufficient: rows without record offsets or
  content hashes are `unevaluable_provenance_missing`.
- P44 public-source materialization remains opt-in, capped at 2,000 records,
  and generated artifacts stay outside the repository unless separately
  reviewed and redacted as fixtures.
- The raw-P44-to-reviewed-local command writes the exact reviewed-local
  manifest schema, privacy/license/citation artifact, private ledger reference,
  pre-label partition manifest, and provenance hashes.
- Legacy `_write_floor_scale_p44_dataset` style rows are covered by explicit
  negative locked tests; embedded labels, families, or partitions from those
  rows cannot satisfy floors.

### P105-014 Partition, coverage, and safety-conformance hardening

Make partition assignment outcome-neutral, compute coverage denominators per
row and partition, and define diagnostic partition scoring.

Acceptance:
- `row_id`, `forecast_id`, `source_window_id`, `incident_group_id`, and
  `partition_id` are deterministic over pre-outcome fields only and do not
  encode label or score outcomes.
- Partitions are predeclared before scoring and preserve time ordering plus
  incident-group isolation; no outcome-shaped reassignment is allowed.
- `covered_seconds` is backed by row coverage intervals and rolled up as the
  union of intervals per `split_id`/`family`/`service`/`source_system` scope.
  False-alert/service-day metrics may not reuse a top-level constant denominator
  or double-count overlapping row coverage.
- Coverage floors use actual source timestamps or reviewed-source timestamp
  bounds only. Synthetic broad intervals, floor-sized intervals, row-count
  duration, and top-level constants are rejected.
- Safety-conformance diagnostic rows with expected precondition violations are
  private-harness only; public/release artifacts publish only violation
  metadata and hash-safe references. Unexpected successful forecasts,
  action-shaped outputs, leaked labels in public/release artifacts, auth paths,
  production mutation, default external calls, or nonzero safety counters fail
  safety.
- Valid and evaluable rows from supported families cannot be excluded from
  performance metrics or moved to diagnostics.

### P105-015 Release documentation, P24 parity, and authority lock

Close the P105 release docs and verification contract without adding auth,
production mutation, or action authority.

Acceptance:
- P105 model card, final summary, release evidence, README, ROADMAP, CHANGELOG,
  and `scripts/verify.sh` docs/tests name the run mode, floors, source
  provenance, P106 gate status, limitations, and stop condition.
- The P24 baseline is actual `RiskSignal`/`RiskForecast` parity from the P24
  implementation, not a simplified reimplementation or fixture-only proxy.
- Release docs preserve the existing P106 thresholds and state that the
  anti-tiny-N floors are credibility floors, not statistical significance
  claims.
- All P105 release outputs keep `auth_enabled=false`,
  `production_mutation_enabled=false`, `action_authority=false`,
  `remediation_execution_enabled=false`, and
  `default_external_model_calls=0`.

### P105-016 Release-qualified evidence contract

Define the G006 contract for a future release-qualified artifact while keeping
the current smoke path locked.

Acceptance:
- `smoke_only` and `smoke_only_missing_mode` evidence always has
  `release_qualified=false` and `p106_unlocked=false`.
- `release_qualified=true` requires every existing P105 floor and every P106
  gate row to be present and passing.
- Missing denominators, missing mode, missing provenance, or unevaluable rows
  fail closed.
- Documentation distinguishes planned acceptance commands from implemented
  behavior.

### P105-017 Deterministic local materializer

Build the local/offline P32/P41/P44 source-record materializer.

Acceptance:
- P32 and P41 consume only repo-local records; P44 is explicit opt-in only and
  capped at 2,000 public-source records.
- Every P32/P41/P44 row includes the canonical six-field source tuple:
  `(source_system, source_dataset, source_manifest_key,
  source_content_hash, materialized_record_hash, materialization_version)`.
- Rows are generated from raw/materialized record bytes plus committed
  metadata, not source ID claims.
- P44 rows are sampled before any label join and cannot use ordinal,
  partition-position, max-value, P24/P105 score, family-floor, or private-label
  signals.
- NAB labels join from official `combined_windows.json` only after sampling;
  missing or unmatched official windows are scorer-negative or unevaluable, not
  relabeled through max-value fallback.
- LogHub incidents come only from the reviewed deterministic error-burst
  scorer ledger with line offsets and source hashes.
- Two runs over the same inputs produce byte-identical rows and manifests.
- A source-availability preflight manifest reports per-family rows, positives,
  incidents, source tuples, review-redaction status, and local hashes before
  scoring.
- P44-disabled negative and reviewed-local P44 positive commands are separate.
- Unique materialized hashes and one row per source-window-incident key prevent
  clone inflation.
- The private ledger includes exact NAB official-window join fields and LogHub
  reviewed error-burst fields after sampling and pre-label partitioning.
- Public features and P24 inputs come from the same raw time window; missing
  source-window identity is unevaluable.

### P105-018 Locked smoke artifact

Keep smoke evidence useful for wiring while making promotion impossible.

Acceptance:
- Smoke artifacts use `smoke_only` or `smoke_only_missing_mode`.
- Tiny-N, hand-computed, fixture-only, and missing-mode runs never satisfy
  release floors or P106 gate rows.
- Smoke and qualified artifacts have separate files, manifests, hashes, mode
  fields, and stop conditions.

### P105-019 Qualified artifact generation

Generate the future `release_qualified` candidate artifact from deterministic
materialized rows.

Acceptance:
- The artifact includes row, source, partition, coverage, P24 parity,
  source-availability preflight, private label, benchmark, review,
  privacy/redaction/license/citation, and provenance-hash manifests with stable
  content hashes.
- Missing privacy, license, citation, source-hash, reviewer, redaction,
  redistribution, private-ledger, or provenance-hash artifacts lock the release
  before benchmark scoring.
- Every supported family passes the exact existing held-out and real-derived
  floors.
- Private label hashes bind labels to canonical tuple, offset, incident group,
  and derivation ID; the private ledger is the metrics source of truth.
- Source diversity uses canonical source tuples and excludes synthetic held-out
  rows from diversity denominators.
- Raw public downloads remain uncommitted; only reviewed, redacted, derived
  artifacts or fixtures may be committed.
- Authority counters remain hard-zero.

### P105-020 Parity, partition, coverage, and isolation

Prove that release metrics are denominator-aligned and not outcome-shaped.

Acceptance:
- P24 baseline rows come from actual P24 `RiskSignal` and `RiskForecast`
  behavior.
- P24 and P105 metrics share rows, split IDs, families, incident matching,
  coverage scopes, and denominators.
- P24 parity is reconstructable per row and the parity manifest includes
  `source_window_id`, input hash, `RiskSignal` hash, `RiskForecast` hash, and
  denominator alignment status.
- Fallback to unrelated seed windows or fixture defaults is forbidden.
- Partition assignment is pre-scoring and outcome-neutral.
- Public features and P24 `TrendWindow` inputs come from the same sampled
  source record/window before private labels are joined.
- Incident groups are created from official NAB windows or the reviewed LogHub
  burst ledger and do not cross partitions.
- False-alert service-day denominators use merged coverage intervals per
  `split_id`/`family`/`service`/`source_system`.

### P105-021 Reproducibility and tamper tests

Make qualified evidence reproducible and tamper-evident.

Acceptance:
- Two materializer runs over the same inputs are byte-identical.
- Source edits, scorer-label edits, row deletion, row duplication, mode edits,
  partition edits, floor weakening, coverage edits, official NAB label edits,
  LogHub burst predicate edits, proxy-mapping edits, privacy/redaction/license
  manifest edits, citation edits, and command-argument edits fail closed.
- Label tamper fails both with unchanged public hashes and with recomputed
  public hashes when the private label ledger no longer matches.
- Any tampered artifact emits `release_qualified=false` and
  `p106_unlocked=false`.

### P105-022 Independent review and full verification

Close G006 only after independent review and full verification.

Acceptance:
- The review ledger records independent review scope, reviewed artifact hash,
  findings, repairs, and final verdict.
- A repair record may state initial `REVISE` and repairs made, but must not
  claim re-approval without a later independent verdict.
- Release docs include locked smoke status, qualified artifact hash, exact
  floors, P106 gate rows, P24 parity, provenance, partition, coverage,
  reproducibility, tamper, privacy, redaction, license, citation, proxy-family
  limitation, and authority evidence.
- Release-gate evidence records RED failures, GREEN commands, output artifact
  paths, artifact hashes, reviewed-local P44 manifest hash, benchmark hash, and
  locked stop reason if honest sources miss unchanged floors.
- P106 unlock claims are absent unless the exact gate payload passes.
- Docs, targeted P105 tests, fast verification, and benchmark commands are
  recorded with results.

## Phase Acceptance

- Forecast output is typed, calibrated, and action-free.
- P24/P25 compatibility is preserved through a versioned adapter with legacy
  prevention plans marked advisory only.
- Time-ordered train/calibration/test splits prevent future-window, incident
  sibling, and scorer-label leakage.
- P24 deterministic baseline is reported with the same denominators as P105.
- Multi-signal features include missingness and provenance.
- Missing-feature, unavailable-evidence, and distribution-shift cases abstain or
  stay conservative.
- Optional NVIDIA rationale is never execution confidence.
- Held-out reports include precision, recall, PR-AUC, Brier, ECE, lead time,
  false alerts/service-day, and abstention rate with exact denominators.
- Release-qualified reports pass the anti-tiny-N held-out and real-derived
  floors, source diversity, service-day coverage, source-record provenance,
  partition isolation, and diagnostic safety semantics. Smoke-only reports never
  unlock P106.
- False-alert service-day denominators are computed from the union of row
  coverage intervals per split/family/service/source scope, not reused
  top-level constants or overlapping row sums.
- P24 baseline parity is measured against actual P24 `RiskSignal` and
  `RiskForecast` behavior.
- Real-derived shadow transfer passes before P106 can start.
- No auth, no production mutation, no remediation execution, and no default
  external model/API calls remain true.

## Stop Condition

P106 is blocked unless calibrated probabilities pass the held-out
time-ordered split, useful lead time transfers to real-derived shadow replay,
and false-alert burden is explicit and within threshold. If any gate fails,
stop at shadow forecasting and do not build speculative preventive action
planning.
