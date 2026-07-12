# P127 Adversarial Test Specification

This specification is a planning handoff for future P127 implementation.
Implementation is pending. It does not require source-code edits, test edits,
credentials, real staging chaos, production chaos, or mutation during this
documentation turn.

## Contract and Authority

- Reject credentials, secrets, real staging targets, production targets, live
  customer connectors, non-lab mutation, free-form action prose, LLM command
  text, and L4+ action requests.
- Require exact-zero counters for credential authority, real staging mutation,
  production mutation, non-lab mutation, and authority escape.
- Require unsafe, ambiguous, stale, partial, or authority-expanding conditions
  to fail closed.

## Fault Injection

- Detect missing evidence, stale evidence, malformed telemetry, corrupt replay,
  clock skew, duplicate events, restart interruption, report-write
  interruption, policy conflict, target ambiguity, validation failure,
  rollback failure, and cleanup failure.
- Require faults to run only in local, sandbox, replay, or disposable-lab
  scope.

## Fail-Closed Behavior

- Detect fail-open action, silent skip, hidden retry, retry storm, missing
  operator reason, missing blocked-action record, missing replay receipt, lost
  audit record, and claim promotion after failure.
- Require operator-visible reasons and durable evidence.

## Named RED Cases

- `fail_open_on_missing_evidence`
- `fail_open_on_target_ambiguity`
- `fail_open_on_policy_conflict`
- `hidden_retry_after_denial`
- `retry_storm`
- `missing_operator_reason`
- `lost_fail_closed_audit`
- `production_chaos_target`
- `real_staging_chaos_target`
- `nonzero_authority_counter`

## Verification Profile

Future implementation must provide targeted P127 verification for fault
catalog coverage, fail-closed decisions, containment, rollback, cleanup, data
preservation, operator-visible reasons, claim controls, and exact-zero
authority counters. Documentation completion does not require those tests to
exist yet.

