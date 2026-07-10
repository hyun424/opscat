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
- Adapter contract test proves P32 contributes only read-only `TrendWindow`
  replay rows and P41 contributes only repo-local source-card-derived rows, with
  scorer labels stripped from public packets.

## Implementation Notes

- Reuse `app/services/real_telemetry_replay_benchmark.py` for observability-
  shaped replay inputs. The P32 adapter may only consume local replay
  `TrendWindow` data, preserve source/window IDs, map `risk_type` to P105
  `family`/`failure_mode`, carry covered-service seconds, and preserve P32
  boundary counters.
- Reuse `app/services/raw_real_dataset_replay.py` for repo-local source-native
  dataset cards. The P41 adapter may only consume source ID, family, labels
  seen, expected labels/root cause/route, parsed record count, and prediction
  evidence; derive label windows from committed source-card metadata; and strip
  scorer-only labels from public packets.
- Shadow forecasting remains non-mutating and cannot emit action plans.
- Neither adapter may add auth, downloads, live API calls, production mutation,
  remediation execution, policy handoff, credential paths, or executable action
  plans.

## Acceptance

- Transfer report includes held-out and real-derived metrics with the same
  formulas and denominators.
- Useful lead time transfers to real-derived shadow replay within configured
  tolerance: absolute useful-lead-time-rate drop is `<= 0.10` per supported
  family and the real-derived rate remains `>= 0.80`.
- False alerts/service-day and abstention rate are explicit by source and
  family.
- Real-derived false-alert transfer allows at most `<= 0.10` absolute increase
  over held-out false alerts/service-day and must still satisfy the per-family
  false-alert threshold.
- Missing real-derived denominators or zero-positive supported families are
  `unevaluable`, not passing.
- P106 remains blocked unless both held-out and real-derived gates pass.

## Verification

Run targeted shadow transfer tests plus existing real telemetry and raw
real-dataset replay tests.
