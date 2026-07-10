# P105-015 - Release Documentation, P24 Parity, and Authority Lock

## Goal

Close P105 with reviewable release docs, actual P24 baseline parity, verify
integration, and an explicit no-authority boundary.

## Tests First

- P24 parity test verifies the baseline uses actual P24 `RiskSignal` and
  `RiskForecast` behavior, including current ETA/confidence/routing semantics,
  rather than a simplified fixture-only proxy.
- Docs contract test requires the P105 model card, final summary, release
  evidence, README, ROADMAP, CHANGELOG, and verify documentation to name run
  mode, floors, source provenance, P106 status, limitations, and stop condition.
- Docs contract test requires release docs to identify current committed P105
  fixtures as `smoke_only_missing_mode` unless explicit release-qualified mode
  metadata and all hardening floors are present.
- Release docs test verifies anti-tiny-N floors are described as credibility
  floors, not statistical significance claims.
- Verify integration test adds P105 docs/release checks without making normal
  verification download public data or call external providers.
- Authority test verifies release outputs keep `auth_enabled=false`,
  `production_mutation_enabled=false`, `action_authority=false`,
  `remediation_execution_enabled=false`, and
  `default_external_model_calls=0`.

## Implementation Notes

- Keep the P106 thresholds unchanged. P105-012 through P105-014 add credibility
  floors and fail-closed release semantics around the thresholds.
- Model card may describe a deterministic rules-plus-calibration system rather
  than a learned model.
- Documentation should state that P106 remains locked unless held-out,
  real-derived, floor, provenance, partition, and safety gates all pass.

## Acceptance

- P105 release evidence is reproducible from committed fixtures and local
  scripts by default.
- P24 baseline rows are direct parity with current P24 behavior.
- README, ROADMAP, CHANGELOG, release evidence, and verify docs do not claim
  production authority, production mutation safety, or P106 unlock from smoke.
- CHANGELOG wording describes P105-012 through P105-015 as planned hardening
  work until implementation and release evidence exist; it must not imply the
  floors, source diversity, or diagnostic harness are already implemented.
- P106 remains blocked whenever any release-hardening requirement is missing,
  failed, or unevaluable.

## Verification

Run docs contract tests, targeted P24 parity tests, P105 release tests, and the
local verification profile after implementation exists.
