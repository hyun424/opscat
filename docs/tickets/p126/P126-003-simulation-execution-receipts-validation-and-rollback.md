# P126-003: simulation, execution receipts, validation, and rollback

## Goal

Define simulation-before-action and receipt requirements for future lab
remediation.

## Contract

- Require simulation receipts before action receipts.
- Require validation and rollback receipts for every action.
- Capture target identity, catalog action, inputs, result, and authority
  counters.

## Acceptance

Future lab remediation evidence can prove what was simulated, executed,
validated, and rolled back.

## Stop Rules

Stop if action occurs without simulation, validation, rollback, or exact target
identity.

