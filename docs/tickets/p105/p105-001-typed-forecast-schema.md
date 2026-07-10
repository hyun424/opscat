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
- Fixture schema test requires each row to include `row_id`,
  `source_window_id`, `family`, `failure_mode`, `service`, `metric`,
  `forecast_timestamp`, `window_start_timestamp`/`window_end_timestamp` or
  `sequence_start`/`sequence_end`, `public_features`, and hidden
  `scorer_labels`.
- Public stripping test rejects public packets that expose `label_incident_id`,
  `label_incident_start_timestamp`, `label_family`, `label_failure_mode`,
  `label_positive`, `lead_time_label_minutes`, `incident_group_id`, or any
  `scorer_labels` member.

## Implementation Notes

- Prefer frozen dataclasses or typed dictionaries colocated with
  `failure_forecast_engine.py`.
- Required forecast fields: `forecast_id`, `source_window_id`, `family`,
  `failure_mode`, `probability`, `probability_interval`, `lead_time_interval`,
  `impact_scope`, `evidence_ids`, `feature_coverage`, `split_id`,
  `model_version`, `rule_version`, and `calibration_version`.
- Required abstention fields: `forecast_id`, `source_window_id`,
  `abstention_reason`, `missing_features`, `coverage`, and `evidence_ids`.
- Required hidden label fields for benchmark fixtures:
  `label_incident_id`, `label_incident_start_timestamp`, `label_family`,
  `label_failure_mode`, `label_positive`, `lead_time_label_minutes`, and
  `incident_group_id`. These fields are scorer-only and never appear in
  training, provider rationale, forecast rendering, or public release packets.
- Release gate summaries must include each metric's formula, numerator,
  denominator, threshold, split ID, family/source scope, and
  pass/fail/unevaluable status.

## Acceptance

- Every forecast and abstention has deterministic serialization.
- Forecasts cite evidence but do not expose action authority.
- Invalid or leaky schema payloads fail closed before benchmark scoring.
- Missing gate denominators, zero denominators without explicit `null` values,
  or leaked scorer labels make the release payload unevaluable and keep P106
  locked.

## Verification

Run targeted schema tests for valid forecasts, abstentions, JSON round trips,
and public-provider packet redaction.
