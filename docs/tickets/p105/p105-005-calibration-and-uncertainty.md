# P105-005 - Calibration and Uncertainty

## Goal

Calibrate forecast probabilities and publish uncertainty intervals without
using LLM confidence as an input to execution authority.

## Tests First

- Calibration-order test proves calibrator fitting uses only the calibration
  split after baseline/model scores are generated.
- Held-out test proves test-set labels are not read before final scoring.
- Reliability test verifies Brier and ECE are computed from calibrated
  probabilities over non-abstained held-out forecasts.
- Improvement test verifies both `p24_brier - p105_brier > 0.0000` and
  `p24_ece - p105_ece > 0.0000` globally and for every supported family with
  `actual_positive_count > 0`.
- Interval test verifies lower/upper probability bounds remain inside `[0, 1]`
  and contain the point estimate.
- LLM guard test proves NVIDIA rationale text cannot change probability,
  interval, threshold, or gate status.

## Implementation Notes

- A deterministic calibration method is sufficient; avoid new dependencies
  unless explicitly approved.
- Publish calibration method, calibration version, bin counts, bin confidence
  means, bin outcome means, and interval method.
- Treat P24 confidence as a baseline score to calibrate or compare, never as
  execution confidence.
- Report calibration metrics as `unevaluable`, not passing, when the
  non-abstained held-out denominator or family positive denominator is missing
  or zero.

## Acceptance

- Held-out Brier and ECE improve over the deterministic P24 baseline, or P105
  release gate fails.
- Improvement is exact: P106 requires positive Brier and ECE improvement
  globally and for every supported family with positives.
- Probability intervals are present for every non-abstained forecast.
- Calibration artifacts are reproducible from split metadata.

## Verification

Run targeted calibration tests and the P105 benchmark command once implemented.
