# P117-005: deterministic selector baseline

## Goal

Implement the release baseline and final fallback: a byte-stable deterministic
selector over sealed evidence, signed action metadata, measured outcomes,
utility, calibration, and abstention rules.

## Contract

- Rank only frozen P115 action-pack IDs and first-class abstention labels.
- Use only P114 visible evidence, P115 signed metadata, P116 measured outcome
  imports, utility policy, calibration policy, and contradiction ledger.
- Emit safe-null fallback labels when evidence, prerequisites,
  contraindications, calibration, utility, or authority boundaries are
  incomplete.
- Produce deterministic receipts for ranking, fallback, citations, utility
  deltas, and replay.

## Acceptance

Repeat agreement is 1.0, harmful-action selection is <= 0.005 overall and 0 for
authority-sensitive families, expected utility uplift versus safe-null baseline
is positive overall and nonnegative per family, and unknown ID count is 0.

## Stop Rules

Stop if the deterministic selector uses hidden labels, row-level split hints,
textual action similarity, unsealed outcomes, or any live authority.
