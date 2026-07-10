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
- Incident matching test proves predicted positives are matched one-to-one to
  actual incidents by family, forecast time, probability, forecast ID, incident
  start time, and incident ID, with duplicate alerts counted as false positives.
- Zero-positive family test proves supported families with
  `actual_positive_count=0` are `unevaluable` for lead-time and calibration
  improvement gates and cannot pass by contributing only to global averages.

## Implementation Notes

- Use the roadmap formulas as the implementation contract.
- Publish threshold, split ID, numerator, denominator, value, and family for
  every metric.
- Report PR-AUC from non-abstained forecasts sorted by calibrated probability
  descending over unique thresholds.
- Match incidents deterministically: sort predicted positives by
  `forecast_timestamp` ascending, calibrated probability descending, then
  `forecast_id` ascending; match to the earliest unmatched actual incident with
  the same family inside the horizon, breaking ties by `label_incident_id`.
- Count a second alert for an already matched incident as a duplicate alert and
  false positive. Count a labeled incident with no matched non-abstained
  forecast as a false negative. Abstentions do not match incidents and do not
  prevent false negatives.

## Acceptance

- Benchmark includes P24 baseline and P105 calibrated rows.
- At least 80% of curated true-positive forecasts have useful positive lead
  time for every supported family with positives.
- Supported families with zero actual positives are marked
  `unevaluable_zero_positive=true`; P106 remains locked until coverage is added
  or the family is removed from the supported set.
- Family-level false-alert burden is explicit and cannot be hidden by a global
  average.
- False alerts/service-day must be `<= 0.25` globally and `<= 0.50` for every
  supported family, with service-day denominators published.
- Missing metric denominators, family counts, service-day denominators, or
  incident counts fail closed before P106 gate evaluation.

## Verification

Run metric unit tests and the P105 forecast benchmark once implemented.
