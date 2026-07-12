# P127-004: claim controls and authority counters

## Goal

Define claim controls and counters for chaos fail-closed evidence.

## Contract

- Classify claims as local/sandbox/replay/lab fail-closed evidence,
  limitation, or forbidden production resilience claim.
- Emit exact-zero credential, real staging, production, non-lab mutation, and
  authority escape counters.
- Block promotion on fail-open or nonzero counters.

## Acceptance

Future reports cannot overclaim chaos evidence as production proof.

## Stop Rules

Stop if reports imply production resilience or omit exact-zero authority
counters.

