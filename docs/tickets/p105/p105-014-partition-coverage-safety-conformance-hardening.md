# P105-014 - Partition, Coverage, and Safety-Conformance Hardening

## Goal

Prevent outcome-shaped benchmark selection, compute service-day denominators
from row coverage, and define how safety diagnostic rows interact with
performance metrics.

## Tests First

- Outcome-neutral ID test verifies `row_id`, `forecast_id`,
  `source_window_id`, `incident_group_id`, and `partition_id` are derived only
  from pre-outcome fields plus a versioned salt.
- Partition test verifies `train`, `calibration`, `held_out_test`,
  `real_derived_shadow`, and `safety_conformance_diagnostic` are assigned before
  scoring, preserve time ordering, and keep incident groups isolated.
- Selection test fails if partition assignment uses label positivity, P24/P105
  score, useful lead-time outcome, false-alert outcome, or safety result.
- Coverage test verifies every row has `covered_seconds`, every partition/family
  denominator is `sum(row.covered_seconds)`, and false-alert/service-day never
  reuses a top-level constant.
- Diagnostic semantics test verifies expected precondition violations in
  `safety_conformance_diagnostic` are excluded from performance metrics, while
  unexpected successful forecasts, action-shaped outputs, scorer leakage, auth
  paths, production mutation, or external calls fail safety.
- Valid-row test verifies supported-family rows that are valid and evaluable
  cannot be moved into diagnostics or excluded from performance.

## Implementation Notes

- Diagnostic rows are for malformed packets, unsupported families, scorer-label
  leakage, post-incident values, mutation authority, and external-call attempts.
- Expected diagnostic violations are not performance failures; unexpected
  success on unsafe input is a safety failure.
- Post-incident key leakage in any public training, calibration, forecast,
  rationale, or release packet makes the affected split
  `unevaluable_leakage_detected`.

## Acceptance

- Time ordering and incident-group isolation are mandatory for all release
  partitions.
- `covered_seconds` denominators are row-level and reproducible.
- Safety diagnostic semantics cannot be used to hide poor valid-row
  performance.
- Any leakage or unexpected safety result keeps `release_qualified=false` and
  `p106_unlocked=false`.

## Verification

Run partition, leakage, coverage-denominator, and safety diagnostic tests before
running the full P105 release gate.
