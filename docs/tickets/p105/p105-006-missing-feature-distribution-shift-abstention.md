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
- False-negative semantics test proves an abstention before a labeled incident
  does not match that incident; if no non-abstained forecast matches it, the
  incident remains a false negative.

## Implementation Notes

- Supported abstention reasons:
  `missing_critical_feature`, `insufficient_p104_evidence`,
  `telemetry_unavailable`, `distribution_shift`, `unsupported_family`,
  `low_service_day_coverage`, and `invalid_split`.
- Publish abstention reason counts globally and per family.
- Include abstentions in abstention-rate denominators.
- Abstentions are excluded from precision, recall, PR-AUC, Brier, ECE,
  true-positive, false-positive, and true-negative denominators. They are
  included only in `abstention_rate = abstained_window_count /
  evaluated_window_count`.
- Gate payloads must publish abstention numerator and denominator globally and
  per supported family; missing abstention denominators are `unevaluable` and
  keep P106 locked.

## Acceptance

- Low-coverage and shifted cases abstain or emit conservative non-actionable
  forecasts.
- Abstention payloads include evidence IDs, missing feature names, coverage, and
  split ID.
- No abstention path creates an executable plan or action handoff.
- Abstention rate must be `<= 0.20` globally and `<= 0.30` for every supported
  family before P106 can unlock.

## Verification

Run targeted abstention tests and benchmark checks that report abstention rate
with numerator and denominator.
