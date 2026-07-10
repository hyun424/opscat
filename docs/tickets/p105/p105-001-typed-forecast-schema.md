# P105-001 - Typed Forecast Schema

## Goal

Define the typed schema for forecast inputs, calibrated forecast outputs,
abstentions, benchmark rows, and release gate summaries.

## Tests First

- Constructor rejects missing forecast IDs, source window IDs, invalid
  probability values, inverted probability intervals, inverted lead-time
  intervals, duplicate evidence IDs, unknown families, and unknown abstention
  reasons.
- JSON round trip preserves P104 `episode_id` and `decision_id`, P24/P25 window
  IDs, family, failure mode, probability interval, impact scope, evidence IDs,
  feature coverage, split ID, model/rule version, and calibration version.
- Public serialization strips scorer-only labels, future outcome timestamps,
  incident-group answer keys, and hidden benchmark fields.

## Implementation Notes

- Prefer frozen dataclasses or typed dictionaries colocated with
  `failure_forecast_engine.py`.
- Required forecast fields: `forecast_id`, `source_window_id`, `family`,
  `failure_mode`, `probability`, `probability_interval`, `lead_time_interval`,
  `impact_scope`, `evidence_ids`, `feature_coverage`, `split_id`,
  `model_version`, `rule_version`, and `calibration_version`.
- Required abstention fields: `forecast_id`, `source_window_id`,
  `abstention_reason`, `missing_features`, `coverage`, and `evidence_ids`.

## Acceptance

- Every forecast and abstention has deterministic serialization.
- Forecasts cite evidence but do not expose action authority.
- Invalid or leaky schema payloads fail closed before benchmark scoring.

## Verification

Run targeted schema tests for valid forecasts, abstentions, JSON round trips,
and public-provider packet redaction.
