# P106-000 - Release Prerequisite and Action-Registry Crosswalk

## Goal

Accept P105 input only through the canonical release-qualified validator and
document the crosswalk from proactive advisory capabilities to registered
action-policy requests.

## Contract

- `P106ReleasePrerequisite` calls
  `validate_p105_release_qualified_artifact(path)` and consumes that report.
- Caller-provided `release_qualified`, `p106_unlocked`, hashes, authority maps,
  timestamps, or copied gate rows are not authority.
- The typed evidence-map row set must equal `G006_P106_GATE_ROWS` exactly:
  `held_out_calibration`, `per_family_release_metrics`,
  `global_release_metrics`, `real_derived_transfer`, and `safety_boundary`.
- `per_family_release_metrics` reads the canonical non-empty
  `release_gate.families[*].pass` mapping. `global_release_metrics` reads
  `release_gate.global.pass`. Guessed raw keys do not pass.
- Authority must exactly equal `G006_ZERO_AUTHORITY`.
- Artifact identity, manifest hashes, and freshness must pass before any
  capability compilation.
- Release smoke input is extracted with
  `scripts/extract_p105_release_fixture.py` from
  `evals/prevention/p105_release_qualified_real_derived.tar.gz` only after its
  SHA-256 matches
  `6aaf35285f03cc7fe68b036a8172dba1615d1e5131939b2d8ef26787dd5c7342`.

## Acceptance

Missing, smoke-only, forged, tampered, stale, wrong-path, wrong-hash, nonzero
authority, validation-error, missing-family, failing-family, or missing-global
artifacts return fail-closed eligibility and do not reach the planner.
