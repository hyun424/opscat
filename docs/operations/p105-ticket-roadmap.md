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

## Tickets

### P105-000 Forecast/action split and P24 compatibility adapter

Introduce the strict forecast/action split and the versioned adapter that keeps
P24/P25 output shape stable while marking legacy prevention output advisory.

Acceptance:
- Calibrated forecast objects contain no executable action list, no action
  route, and no policy handoff field.
- P24/P25 compatibility output still contains `prevention_plan`, but it is
  labeled `legacy_advisory=true`, `action_execution_enabled=false`, and
  `p106_required_for_execution=true`.
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
  globally and no family hides behind a global average.

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
- If the gate fails, the release summary explicitly stops at shadow forecasting.

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
- Real-derived shadow transfer passes before P106 can start.
- No auth, no production mutation, no remediation execution, and no default
  external model/API calls remain true.

## Stop Condition

P106 is blocked unless calibrated probabilities pass the held-out
time-ordered split, useful lead time transfers to real-derived shadow replay,
and false-alert burden is explicit and within threshold. If any gate fails,
stop at shadow forecasting and do not build speculative preventive action
planning.
