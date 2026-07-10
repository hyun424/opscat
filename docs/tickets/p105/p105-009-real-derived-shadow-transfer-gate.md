# P105-009 - Real-Derived Shadow Transfer Gate

## Goal

Prove that held-out calibration behavior transfers to real-derived,
source-native shadow replay before P106 can start.

## Tests First

- P32 replay integration test consumes local real telemetry replay trend windows
  without live API calls or remediation execution.
- P41 raw replay integration test consumes source-native raw dataset cards
  without downloads, auth, or live API calls.
- Shadow report test compares synthetic held-out metrics to real-derived shadow
  metrics by family, source, lead time, false-alert burden, and abstention.
- Gate test proves `p106_unlocked` remains false if held-out thresholds pass but
  real-derived transfer thresholds fail.

## Implementation Notes

- Reuse `app/services/real_telemetry_replay_benchmark.py` for observability-
  shaped replay inputs.
- Reuse `app/services/raw_real_dataset_replay.py` for repo-local source-native
  dataset cards.
- Shadow forecasting remains non-mutating and cannot emit action plans.

## Acceptance

- Transfer report includes held-out and real-derived metrics with the same
  formulas and denominators.
- Useful lead time transfers to real-derived shadow replay within configured
  tolerance.
- False alerts/service-day and abstention rate are explicit by source and
  family.
- P106 remains blocked unless both held-out and real-derived gates pass.

## Verification

Run targeted shadow transfer tests plus existing real telemetry and raw
real-dataset replay tests.
