# P124-004: leakage, claim controls, and authority counters

## Goal

Define leakage detection, claim controls, and authority counters for P124.

## Contract

- Detect hidden-truth leakage across prompts, reports, logs, case IDs, and
  metadata.
- Classify claims as offline quality evidence, limitation, or forbidden
  production/operator-replacement claim.
- Emit exact-zero authority counters.

## Acceptance

Future verification blocks leaked, overclaimed, or authority-expanding
evaluation reports.

## Stop Rules

Stop if hidden truth leaks, claims imply production accuracy, or any authority
counter is nonzero.

