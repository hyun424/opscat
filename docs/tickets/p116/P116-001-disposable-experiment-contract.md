# P116-001: disposable experiment contract

## Goal

Define the immutable lab experiment schema used by every P116 fixture, action
arm, reset, rollback, outcome record, and replay receipt.

## Contract

- Include schema version, experiment ID, scenario ID, fixture version, seed,
  fault family, split, arm name, action plan ID, observation windows, reset
  plan, rollback plan, authority declaration, and hidden scorer handle.
- Bind public initial state through an `initial_condition_fingerprint` that
  excludes arm name, hidden labels, selected action, and expected outcome.
- Require `lab_only=true`, `production_authority=false`,
  `credential_scope=false`, and `p118_required_for_canary=true`.
- Separate proposal, lab execution receipt, observation, rollback, reset, and
  replay fields.
- Reject unknown major schema versions and missing required denominators.

## Acceptance

Contract tests reject production references, credentials, external cluster
contexts, missing reset or rollback plans, mutable IDs, hidden-label exposure,
and copied success booleans. A valid contract is sufficient only for lab
planning; it grants no execution authority.
