# P105-012 - Release Qualification Floors and Mode Semantics

## Goal

Make P105 release evidence credible by separating wiring smoke from
release-qualified evaluation. Tiny fixtures can prove formulas, but they cannot
unlock P106.

## Tests First

- Mode test verifies missing mode metadata defaults to `smoke_only`.
- Smoke gate test verifies tiny, hand-computed, and fixture-only runs always
  emit `release_qualified=false` and `p106_unlocked=false`.
- Held-out floor test verifies every supported family must satisfy
  `evaluated >= 30`, `non_abstained >= 24`, `actual_positive >= 6`,
  `incident_group_count >= 4`, and `covered_service_seconds / 86400 >= 2.0`.
- Real-derived floor test verifies every supported family must satisfy
  `evaluated >= 20`, `non_abstained >= 16`, `actual_positive >= 4`,
  `incident_group_count >= 3`, and `covered_service_seconds / 86400 >= 1.0`.
- Diversity test verifies at least three distinct source record sets across
  P32/P41/P44 materialized inputs, no source supplies more than 60% of any
  supported family's release-qualified rows, and global service coverage is at
  least seven service-days.
- Fail-closed test verifies any missing numerator, denominator, source count,
  incident-group count, coverage value, split ID, family ID, or mode field makes
  the release `unevaluable_missing_denominator`.

## Implementation Notes

- These floors preserve the existing P106 thresholds. They are anti-tiny-N
  credibility floors, not statistical significance claims.
- Floor values are sized for the existing P44 max-2,000-record public-source
  path plus committed P32/P41 materialized replay fixtures.
- If a supported family cannot meet the floors, keep the run `smoke_only` or
  remove the family from `supported_families` before release qualification.

## Acceptance

- Only `release_qualified` runs can evaluate `p106_unlocked=true`.
- Smoke and tiny-N runs can never unlock P106.
- Every floor publishes numerator, denominator, split ID, source scope, family,
  threshold, value, and pass/fail/unevaluable status.
- P106 remains locked when any floor is missing, failed, or unevaluable.

## Verification

Run targeted release-mode and floor-contract tests plus docs checks that prove
the model card and release evidence explain the anti-tiny-N scope.
