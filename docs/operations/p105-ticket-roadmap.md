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
  `service_days` is the sum of covered seconds per service divided by 86400 for
  the evaluated split. Publish service-day coverage per family.
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
  this roadmap. Missing mode metadata is `smoke_only` by default.

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
  the release, and no single source may contribute more than `0.60` of a
  supported family's release-qualified rows:
  `max_source_family_row_count / family_release_row_count <= 0.60`.
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
- `covered_seconds`: row-level service coverage denominator used by
  false-alert/service-day scoring.
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

P44 adapter responsibilities for P105 are limited to read-only transformation of
explicitly materialized public-source records, capped at 2,000 records per
opt-in public run. The adapter must generate rows from raw/materialized record
content and hashes, not from source ID claims alone. Public downloads remain
explicit opt-in and generated artifacts remain outside the repository unless
converted into reviewed, redacted fixtures.

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

Safety-conformance diagnostic rows exist only to prove boundary handling for
expected invalid preconditions such as malformed public packets, unsupported
families, leaked scorer labels, post-incident values, mutation authority, or
external-call attempts. Expected precondition violations in this partition are
excluded from performance metrics, but any unexpected successful forecast,
unexpected action-shaped output, credential/auth path, production mutation,
default external call, or nonzero safety counter fails the safety gate. Valid
and evaluable rows from supported families may never be moved into
`safety_conformance_diagnostic` or excluded from performance to improve scores.

Post-incident key leakage fails closed. If a public training, calibration,
forecast, rationale, or release packet contains post-incident values,
scorer-only labels, incident IDs, incident-group answer keys, lead-time labels,
future timestamps, or hashes derived from those fields, the affected split is
`unevaluable_leakage_detected`, `release_qualified=false`, and
`p106_unlocked=false`.

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
- Release evidence proves at least three distinct source record sets across
  P32/P41/P44 materialized inputs, no single source contributes more than 60%
  of any supported family's release-qualified rows, and global service coverage
  is at least seven service-days.
- Missing floor denominators or mode metadata fail closed as
  `unevaluable_missing_denominator`.

### P105-013 Deterministic source-record row generation

Build the P32/P41/P44 row-generation contract from raw/materialized source
records with content hashes and derivation metadata.

Acceptance:
- Every row records source system, source path or manifest key, source content
  hash, materialized record hash, record offset or row index, source timestamp
  when available, materialization version, source-window derivation,
  evidence-ID derivation, family derivation, and label derivation.
- Re-running the generator from the same raw/materialized inputs produces
  byte-identical rows and partition manifests.
- Source-ID-only assertions are insufficient: rows without record offsets or
  content hashes are `unevaluable_provenance_missing`.
- P44 public-source materialization remains opt-in, capped at 2,000 records,
  and generated artifacts stay outside the repository unless separately
  reviewed and redacted as fixtures.

### P105-014 Partition, coverage, and safety-conformance hardening

Make partition assignment outcome-neutral, compute coverage denominators per
row and partition, and define diagnostic partition scoring.

Acceptance:
- `row_id`, `forecast_id`, `source_window_id`, `incident_group_id`, and
  `partition_id` are deterministic over pre-outcome fields only and do not
  encode label or score outcomes.
- Partitions are predeclared before scoring and preserve time ordering plus
  incident-group isolation; no outcome-shaped reassignment is allowed.
- `covered_seconds` is present per row and rolled up per partition/family/source
  as `sum(row.covered_seconds)`. False-alert/service-day metrics may not reuse
  a top-level constant denominator.
- Safety-conformance diagnostic rows with expected precondition violations are
  excluded from performance metrics, but unexpected successful forecasts,
  action-shaped outputs, leaked labels, auth paths, production mutation,
  default external calls, or nonzero safety counters fail safety.
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
- False-alert service-day denominators are computed from per-row/per-partition
  `covered_seconds`, not reused top-level constants.
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
