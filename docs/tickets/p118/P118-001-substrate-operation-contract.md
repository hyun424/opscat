# P118-001: substrate operation contract

## Goal

Define the immutable P118 operation envelope, lifecycle states, action levels,
fixture target rules, receipts, terminal statuses, and rejected authority
fields for local/mock/sandbox execution only.

## Contract

- Define `p118.operation_envelope.v1` with operation ID, schema version, P117
  decision episode ID, P117 selected action-pack ID, P115 action-pack digest,
  fixture target ID, action level, preconditions, validation plan, rollback
  plan, approval receipt, lease receipt, WAL position, CAS version,
  idempotency key, and authority counter snapshot.
- Define lifecycle states from receipt through verification, approval,
  precheck, action attempt, postcheck, rollback, rollback postcheck, terminal
  replay, and final report.
- Support only L0-L3 action levels against local/mock/sandbox fixture targets.
- Define terminal statuses for success, validation failure, rollback success,
  rollback failure, rejection, expiry, orphan recovery, and fail-closed abort.
- Reject auth context, credentials, secrets, production target selectors, live
  connectors, shell text, subprocess commands, Kubernetes/cloud/database/
  network mutation fields, online policy writes, free-form action prose, and
  L4+ action requests.

## Acceptance

Contract validity is 1.0 on valid local fixtures, rejected authority fields are
accepted 0 times, serialization is deterministic, L3 is the maximum accepted
level, and auth/credential/production-mutation counters remain exactly zero.

## Stop Rules

Stop if the contract permits auth, credentials, production mutation, live
connectors, online policy writes, executable commands, free-form actions, L4+
authority, missing receipts, or optimistic terminal statuses.
