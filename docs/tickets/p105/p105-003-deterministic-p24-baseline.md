# P105-003 - Deterministic P24 Baseline

## Goal

Freeze the current P24 slope/threshold forecast as the deterministic baseline
for every P105 calibration and benchmark claim.

## Tests First

- Baseline parity test reproduces P24 `RiskSignal.from_window` ETA and
  confidence for P25 fixture windows.
- Route parity test reproduces current `ProactiveRiskSentinel._forecast` routes:
  `preventive_review`, `monitor`, and `blocked`.
- Benchmark parity test emits precision, recall, PR-AUC, Brier, ECE, lead time,
  false alerts/service-day, and abstention rate using the same denominators as
  P105.
- Determinism test proves repeated baseline runs produce byte-identical JSON.

## Implementation Notes

- Treat P24 confidence as an uncalibrated baseline score, not a probability with
  execution authority.
- Keep baseline local/mock, deterministic, and network-free.
- Publish baseline model version separately from calibrated model version.

## Acceptance

- P105 reports always include the P24 baseline row.
- Brier and ECE improvement claims compare against this frozen baseline.
- Existing P24/P25 release tests keep passing through the compatibility adapter.

## Verification

Run P105 baseline tests plus `tests/test_proactive_risk_sentinel.py` and
`tests/test_p25_proactive_corpus_calibration.py`.
