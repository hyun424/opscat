# P105-000 - Forecast/Action Split and P24 Compatibility Adapter

## Goal

Create the contract that separates calibrated failure forecasts from any
action-shaped prevention plan while preserving the P24/P25 public payload
through a versioned compatibility adapter.

## Tests First

- Adapter test proves every calibrated forecast has no executable action list,
  no policy handoff route, and no remediation capability field.
- Compatibility test proves the P24/P25 output shape still includes
  `prevention_plan`, but it is marked `legacy_advisory=true`,
  `action_execution_enabled=false`, and `p106_required_for_execution=true`.
- Regression test proves P24/P25 calibration fixtures can still be rendered
  without changing existing fixture IDs or risk types.
- Safety test proves advisory prevention plans cannot be consumed as P106 action
  requests.

## Implementation Notes

- Extend `app/services/proactive_risk_sentinel.py` only through a compatibility
  adapter or thin versioned wrapper.
- Add the calibrated engine in a separate module such as
  `app/services/failure_forecast_engine.py`.
- Keep existing P24 baseline logic intact for `RiskSignal.from_window` and
  `ProactiveRiskSentinel`.

## Acceptance

- Forecast output is action-free.
- Legacy prevention content remains visible only as advisory compatibility data.
- No auth, production mutation, remediation execution, or default external model
  call path is added.

## Verification

Run targeted P105 forecast/action split tests plus existing P24/P25 proactive
sentinel and calibration tests.
