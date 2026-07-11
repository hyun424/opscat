# P119-005: local execution, validation, rollback, and false-recovery gate

## Goal

Submit approved local fixture operations through P118-style envelopes, verify
measured recovery, roll back unsafe or ambiguous outcomes, and prevent false
recovery declarations.

## Contract

- Run local operations only after approval receipt, operation envelope, WAL
  receipt, CAS success, owner lease, validation plan, rollback plan, and
  exact-zero authority snapshot exist.
- Bind every operation to fixture target ID, frozen action-pack digest,
  preconditions, validation probes, rollback probes, and idempotency key.
- Require measured postcheck evidence inside the validation observation window
  before any recovery claim.
- Trigger rollback for action failure, failed postcheck, guardrail breach,
  collateral harm, unsafe partial state, ambiguous recovery, or attribution
  uncertainty when rollback metadata exists.
- Record rollback evidence, rollback postcheck evidence, final status,
  timeline refs, and replay bundle refs.

## Acceptance

No local operation runs without required receipts, duplicate local action
attempts remain zero, validation evidence is measured and hash-bound, rollback
and rollback postcheck are visible, and `recovered` cannot be emitted until
postcheck, attribution, recurrence, and authority gates pass.

## Stop Rules

Stop if execution can target production or staging, run live connectors,
execute shell/subprocess/Kubernetes/cloud/database/network mutation, bypass
approval or leases, skip rollback, hide failed postchecks, credit rollback as
action success, or declare recovery without measured evidence.
