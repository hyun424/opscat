# P105-008 - Per-Family Lead-Time and False-Alert Benchmark

## Goal

Build the benchmark report that scores P105 and the deterministic P24 baseline
with exact formulas, denominators, and per-family tables.

## Tests First

- Metric formula tests verify precision, recall, PR-AUC, Brier, ECE, lead time,
  false alerts/service-day, useful lead-time rate, and abstention rate on small
  hand-computed fixtures.
- Denominator tests verify zero-denominator metrics report `null` plus explicit
  numerator and denominator rather than silently returning zero.
- Per-family test proves every metric is emitted globally and by family/severity.
- Service-day test verifies false alerts/service-day uses covered service
  seconds divided by 86400.

## Implementation Notes

- Use the roadmap formulas as the implementation contract.
- Publish threshold, split ID, numerator, denominator, value, and family for
  every metric.
- Report PR-AUC from non-abstained forecasts sorted by calibrated probability
  descending over unique thresholds.

## Acceptance

- Benchmark includes P24 baseline and P105 calibrated rows.
- At least 80% of curated true-positive forecasts have useful positive lead
  time globally.
- Family-level false-alert burden is explicit and cannot be hidden by a global
  average.

## Verification

Run metric unit tests and the P105 forecast benchmark once implemented.
