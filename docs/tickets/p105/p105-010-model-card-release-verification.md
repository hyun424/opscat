# P105-010 - Model Card and Release Verification

## Goal

Document the forecast engine, calibration method, data boundaries, metrics,
limitations, and release evidence needed to review P105 safely.

## Tests First

- Docs contract test requires the P105 final summary and model card to list data
  sources, split IDs, feature families, calibration method, thresholds,
  abstention policy, limitations, and non-goals.
- Release evidence test requires P24 baseline metrics, calibrated P105 metrics,
  shadow transfer metrics, safety counters, and P106 gate status.
- Boundary test requires no auth, no production mutation, no remediation
  execution, no default external calls, and no scorer leakage.

## Implementation Notes

- Add final summary only during implementation closeout, not in this planning
  artifact commit.
- Keep release evidence local/offline by default.
- Include a model/rule card because P105 may be deterministic rules plus
  calibration rather than a learned model.

## Acceptance

- Model card makes thresholds and abstention behavior reviewable.
- Release evidence can be reproduced from committed fixtures and local scripts.
- Known limitations are explicit, especially for unsupported families and low
  service-day coverage.

## Verification

Run docs contract tests, targeted P105 release tests, and the local verification
profile once implementation exists.
