# P105-006 - Missing-Feature and Distribution-Shift Abstention

## Goal

Fail closed or stay conservative when feature coverage, evidence sufficiency, or
distribution similarity is not good enough for a calibrated forecast.

## Tests First

- Missing critical feature test emits `missing_critical_feature` abstention.
- P104 evidence gap test emits `insufficient_p104_evidence` when the envelope is
  not sufficient for downstream forecast use.
- Telemetry outage test distinguishes `telemetry_unavailable` from valid absence
  evidence.
- Distribution-shift test emits `distribution_shift` when held-out feature
  values fall outside configured train/calibration reference ranges.
- Gate test proves abstained forecasts cannot unlock P106.

## Implementation Notes

- Supported abstention reasons:
  `missing_critical_feature`, `insufficient_p104_evidence`,
  `telemetry_unavailable`, `distribution_shift`, `unsupported_family`,
  `low_service_day_coverage`, and `invalid_split`.
- Publish abstention reason counts globally and per family.
- Include abstentions in abstention-rate denominators.

## Acceptance

- Low-coverage and shifted cases abstain or emit conservative non-actionable
  forecasts.
- Abstention payloads include evidence IDs, missing feature names, coverage, and
  split ID.
- No abstention path creates an executable plan or action handoff.

## Verification

Run targeted abstention tests and benchmark checks that report abstention rate
with numerator and denominator.
