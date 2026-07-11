# P118-006: validation, rollback, and postcheck

## Goal

Define precheck, validation, action, postcheck, rollback, rollback validation,
rollback evidence, and final status semantics without optimistic success.

## Contract

- Run precheck before action and record measured evidence hashes.
- Attempt action only after verification, approval, lease ownership, WAL append,
  CAS transition, idempotency check, and clean authority counters.
- Run postcheck after action and require measured evidence before `succeeded`.
- Trigger rollback on action failure, postcheck failure, unsafe partial state,
  or configured rollback condition.
- Run rollback postcheck and record rollback evidence before `rolled_back`.
- Preserve `validation_failed`, `rollback_failed`, and `aborted_fail_closed` as
  explicit terminal statuses.
- Reject validation probes, rollback probes, and status reports that contain
  production targets, credentials, auth context, live connectors, shell text,
  subprocess commands, online policy writes, or L4+ authority.

## Acceptance

Optimistic success count is 0, missing-postcheck success count is 0,
rollback-without-evidence count is 0, rollback failure is visible, and every
final status includes evidence hashes plus exact authority counters.

## Stop Rules

Stop if success can be reported without postcheck evidence, rollback can be
skipped or hidden, rollback postcheck is optional, validation touches live
systems, failed rollback is masked as success, or authority counters drift.
