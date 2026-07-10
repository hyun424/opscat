# P105-002 - Leakage-Resistant Time-Ordered Split

## Goal

Create the train/calibration/test split contract that prevents future-window,
incident-sibling, and scorer-label leakage.

## Tests First

- Split builder test proves train timestamps precede calibration timestamps and
  calibration timestamps precede test timestamps.
- Incident-group isolation test proves all windows from one incident group stay
  in exactly one split.
- Leakage test fails when a later point from the same incident appears in an
  earlier split's features.
- Public feature packet test proves outcome labels, incident start timestamps,
  post-incident values, and scorer-only fields are absent from training inputs.
- Public stripping test proves `label_incident_id`,
  `label_incident_start_timestamp`, `label_family`, `label_failure_mode`,
  `label_positive`, `lead_time_label_minutes`, `incident_group_id`, and the
  full `scorer_labels` object are available only to the scorer after forecasts
  are produced.

## Implementation Notes

- Add split metadata under `evals/proactive/forecast/` during implementation.
- Use deterministic sequence IDs only when source timestamps are unavailable.
- Record split ID, family coverage, service-day coverage, incident-group count,
  time range, and overlap hashes.
- Fixture rows use `forecast_timestamp`, `window_start_timestamp`, and
  `window_end_timestamp`; deterministic `sequence_start`/`sequence_end` may be
  used only when source timestamps are unavailable and must be ordered the same
  way as timestamps.

## Acceptance

- Random window splits are not allowed.
- Future evidence and post-incident labels cannot influence train or
  calibration features.
- Split reports publish enough metadata to reproduce benchmark denominators.
- Any public split packet containing scorer-only label fields fails closed
  before calibration, scoring, or P106 gate evaluation.

## Verification

Run targeted split-contract tests and inspect generated split metadata in the
P105 benchmark report.
