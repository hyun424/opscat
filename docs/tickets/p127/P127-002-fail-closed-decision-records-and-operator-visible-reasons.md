# P127-002: fail-closed decision records and operator-visible reasons

## Goal

Define durable fail-closed records for future chaos tests.

## Contract

- Record failure reason, blocked action, policy rule, evidence state, replay
  receipt, and operator-visible message.
- Reject silent skips, hidden retries, and ambiguous pass states.
- Preserve records across restart.

## Acceptance

Future operators can inspect why OpsCat refused continuation.

## Stop Rules

Stop if fail-closed behavior lacks durable records or operator-visible
reasons.

