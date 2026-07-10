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

## Implementation Notes

- Add split metadata under `evals/proactive/forecast/` during implementation.
- Use deterministic sequence IDs only when source timestamps are unavailable.
- Record split ID, family coverage, service-day coverage, incident-group count,
  time range, and overlap hashes.

## Acceptance

- Random window splits are not allowed.
- Future evidence and post-incident labels cannot influence train or
  calibration features.
- Split reports publish enough metadata to reproduce benchmark denominators.

## Verification

Run targeted split-contract tests and inspect generated split metadata in the
P105 benchmark report.
