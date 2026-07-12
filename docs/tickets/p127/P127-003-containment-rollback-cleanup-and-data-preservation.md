# P127-003: containment, rollback, cleanup, and data preservation

## Goal

Define containment and durability checks for future chaos failures.

## Contract

- Detect hidden mutation, retry storms, data loss, duplicate records, rollback
  failure, and cleanup failure.
- Preserve audit, replay, authority rejection, and fail-closed records.
- Require rollback and cleanup receipts where lab actions are involved.

## Acceptance

Future chaos evidence can show failures are contained and records are not
lost.

## Stop Rules

Stop if faults cause hidden mutation, unbounded retry, lost records, or
unreported rollback failure.

