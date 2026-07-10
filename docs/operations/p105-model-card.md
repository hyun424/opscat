# P105 model card - Calibrated Failure Forecast Engine

## Status

P105 forecasts concrete operational failure families and modes from local,
offline evidence. It does not plan or execute actions. The current committed
fixture is `smoke_only_missing_mode`: it is useful for wiring, formulas, and
release-contract tests, but it is too small to be release-qualified and cannot
unlock P106.

P106 remains locked unless a future generated payload declares
`mode=release_qualified`, passes every qualification floor, passes every metric
gate, and keeps every authority counter at zero.

## Inputs and provenance

Release-qualified rows must derive from materialized P32/P41/P44 source records:

- P32 telemetry replay records from `evals/telemetry/replay/p32_replay_pack.json`.
- P41 raw source-card records from `evals/real_datasets/raw/p41_sources.json`.
- P44 public matrix records from
  `evals/real_datasets/external/p44_benchmark_matrix_manifest.json`.

Each release row must carry canonical source tuple, source content hash,
materialized source-record hash, byte offset or record offset, source timestamp
when available, deterministic derivation ID, partition ID, coverage intervals,
and scorer-only labels separated from public features. Source-ID-only
provenance is not enough for release qualification.

## Modes

- `smoke_only`: bounded local verification for tiny fixtures and hand-computed
  formula cases. It can prove wiring but cannot unlock P106.
- `smoke_only_missing_mode`: deterministic fail-closed normalization for
  missing, empty, null, or unknown mode metadata.
- `release_qualified`: the only mode eligible to evaluate `p106_unlocked=true`.

The committed P105 fixture has no mode metadata and therefore normalizes to
`smoke_only_missing_mode`.

## Qualification floors

For every supported release family:

- Held-out floor: evaluated windows >= 30, non-abstained forecasts >= 24,
  actual positives >= 6, incident groups >= 4, and service days >= 2.0.
- Real-derived floor: evaluated windows >= 20, non-abstained forecasts >= 16,
  actual positives >= 4, incident groups >= 3, and service days >= 1.0.
- Source diversity: at least three distinct P32/P41/P44 source record sets, and
  no single canonical source tuple may contribute more than 60% of a supported
  family's release-qualified real-derived rows.
- Global service-day coverage: merged held-out plus real-derived service-day
  coverage >= 7.0.

These floors are anti-tiny-N credibility checks, not statistical significance
claims.

## Metrics

All release reports must publish numerators, denominators, family or source
scope, split ID, formula, threshold, and pass/fail/unevaluable status.

- `precision = true_positive / (true_positive + false_positive)`.
- `recall = true_positive / (true_positive + false_negative)`.
- `Brier = sum((p_i - y_i)^2) / N`.
- `ECE` uses 10 fixed probability bins and sums
  `abs(mean(p_b) - mean(y_b)) * n_b / N`.
- `useful_lead_time_rate =
  useful_true_positive_count / true_positive_count`.
- `false_alerts_per_service_day = false_positive_count / service_days`, where
  `service_days` comes from the union of coverage intervals for the evaluated
  split/family/service/source scope.
- `abstention_rate = abstained_window_count / evaluated_window_count`.

Zero denominators are reported as `null` metrics with explicit zero
denominators. Missing denominators fail closed.

## P24 parity

The P105 release gate must compare against actual P24
`app.services.proactive_risk_sentinel.RiskSignal` and `RiskForecast` output for
the same windows. Mocked or source-ID-only parity is insufficient for release
qualification.

## Limitations

P105 does not prove production failure prediction quality, live connector
correctness, customer readiness, unattended operation, or operator replacement.
The committed fixture is small and synthetic/local-derived. Release-qualified
performance claims require generated evidence at the floors above.

## Authority boundary

P105 has no auth, no production mutation, no remediation execution, no
executable action plan, no provider action authority, no default external model
calls, and no P106 action-planning authority. Optional model rationale remains
advisory only and cannot raise confidence or unlock P106.

## Commands

Offline smoke:

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark evals/proactive/forecast/p105_release_benchmark_rows.json \
  --output-json /tmp/opscat-p105-release-benchmark-smoke.json
```

Targeted tests:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_failure_forecast_engine.py \
  tests/test_p105_release_evidence.py
```
