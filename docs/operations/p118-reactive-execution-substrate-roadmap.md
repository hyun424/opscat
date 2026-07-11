# P118 Reactive Execution Substrate Roadmap / PRD

## Objective

P118 plans a local/mock/sandbox reactive execution substrate that can execute
only signed, frozen P115 action packs selected by P117 under deterministic
gates. It turns frozen action-pack IDs into auditable sandbox operations with
WAL, CAS, idempotency, leases, approval, validation, rollback, crash recovery,
and frozen fail-closed evaluation.

P118 does not authorize production mutation, authentication, credentials, live
connector access, online policy writes, or broad autonomous remediation.

This roadmap is documentation-only. It does not create source-code work,
runtime authority, production access, or implementation permission by itself.

## Source Context

- P115 defines signed action packs, action/non-action labels, prerequisites,
  contraindications, validation metadata, rollback metadata, and authority
  counters.
- P116 defines local lab controls for action, no-action, wrong-action,
  rollback, crash recovery, idempotency, concurrency, orphan cleanup, reset, and
  replay.
- P117 selects frozen P115 action-pack IDs or abstention labels as
  proposal-only benchmark decisions. P117 requires P118 for any execution and
  does not grant execution authority.

## Product Claim

P118 may claim only "local/mock/sandbox reactive execution substrate readiness"
after frozen evaluation and independent review pass.

It may not claim production-safe autonomous remediation, operator replacement,
live canary execution, production readiness, credential handling, or L4+
execution.

## Non-Authority Boundary

Every P118 artifact preserves these invariants:

- auth is deferred;
- credential and secret scopes are absent;
- maximum action level is L3;
- local/mock/sandbox fixture targets are the only valid targets;
- staging and production Kubernetes, cloud, database, network, connector, and
  policy targets are rejected;
- production mutation, online policy writes, live connector calls, shell, and
  subprocess execution remain unavailable;
- free-form action prose, LLM-generated commands, and invented action IDs are
  rejected;
- auth, credential, executor, shell, subprocess, Kubernetes, cloud, database,
  production-adapter, network, online-policy, and production-mutation counters
  remain exactly zero.

## Operation Contract

Each operation is an immutable envelope:

```text
operation_id
schema_version
p117_decision_episode_id
p117_selected_action_pack_id
p115_action_pack_digest
fixture_target_id
action_level
precondition_refs
validation_plan_ref
rollback_plan_ref
approval_receipt
lease_receipt
wal_position
cas_version
idempotency_key
authority_counter_snapshot
```

The substrate rejects any envelope containing credentials, auth context,
production target selectors, shell text, subprocess commands, free-form action
instructions, live connector names, online policy write fields, or L4+ levels.

Terminal statuses are explicit: `succeeded`, `rolled_back`,
`rollback_failed`, `validation_failed`, `rejected`, `expired`,
`orphaned_recovered`, and `aborted_fail_closed`.

## WAL, CAS, Idempotency, and Leases

P118 records every state transition in an append-only WAL receipt log with
hash chaining. Runtime state advances only through compare-and-set transitions
from the current CAS version. A single owner lease controls execution. Lease
renewal, expiry, retry, and takeover are recorded as receipts.

Idempotency keys bind operation ID, action-pack digest, fixture target, and
precondition hash. Repeated submission with the same key returns the existing
operation state. Conflicting payloads for a used key fail closed. Terminal
replay is read-only and must reconstruct the same operation status, counters,
and evidence hashes without re-running actions.

## Signed Action-Pack Verification

Before approval or execution, P118 verifies:

- signer identity and signature validity;
- digest and schema version;
- expiration and revocation status;
- allowed level no higher than L3;
- local/mock/sandbox fixture target binding;
- validation and rollback plan presence;
- prerequisite and contraindication receipts;
- exact match between the P117 selected frozen action-pack ID and the P115
  signed action pack.

Unsigned, stale, revoked, mismatched, production-like, auth-bearing, or
command-bearing packs fail closed.

## Approval Policy

Approval is deterministic. The policy can approve only local/mock/sandbox L0-L3
action packs that pass signature, digest, schema, target, precondition,
contraindication, validation, rollback, lease, WAL, CAS, idempotency, and
authority-counter gates.

Anything auth-bearing, credential-bearing, production-like, stale, unsigned,
revoked, contraindicated, above L3, missing rollback, missing validation, or
with nonzero authority counters is rejected.

## Validation and Rollback

The operation lifecycle is:

```text
received -> verified -> approved -> prechecked -> action_attempted ->
postchecked -> succeeded
```

Failure paths are explicit:

```text
precheck_failed -> rejected
action_failed -> rollback_attempted -> rollback_postchecked
postcheck_failed -> rollback_attempted -> rollback_postchecked
rollback_failed -> rollback_failed
```

No optimistic success is allowed. Success requires measured postcheck evidence.
Rollback requires rollback evidence and rollback postcheck evidence. Final
status includes all measured evidence hashes and exact authority counters.

## Crash Recovery

P118 must recover from crashes before and after precheck, action, postcheck,
rollback, rollback postcheck, and report write. Recovery uses WAL receipts,
CAS versions, idempotency keys, lease expiry, and orphan inventory. Duplicate
action attempts are prevented or counted as release blockers. Replay must
produce the same terminal state without hidden mutation.

## Frozen Evaluation

Release evaluation freezes:

- operation fixtures;
- signed action packs;
- P117 selected IDs;
- policy configuration;
- validation probes;
- rollback probes;
- crash matrix;
- lease and CAS conflict cases;
- WAL corruption cases;
- authority scan rules;
- seeds and split assignments;
- release thresholds;
- evidence bundle hashes;
- independent review inputs.

The first frozen score consumes the evaluation split. Any tampering, stale hash,
self-review, nonzero authority counter, production-like target, or fail-open
behavior blocks release.

## Ticket Sequence

1. P118-001 substrate operation contract.
2. P118-002 WAL, CAS, and idempotency ledger.
3. P118-003 lease owner and reactive worker loop.
4. P118-004 signed action-pack verification.
5. P118-005 approval policy and authority counters.
6. P118-006 validation, rollback, and postcheck.
7. P118-007 crash recovery and replay.
8. P118-008 frozen evaluation and release gates.

## Acceptance Gates

P118 can claim local/mock/sandbox reactive execution substrate readiness only
when one fresh evidence set proves:

- all operation contracts reject auth, credentials, production mutation,
  command text, live connectors, online policy writes, and L4+ levels;
- signed action-pack verification fails closed for unsigned, stale, revoked,
  mismatched, or production-like packs;
- WAL hash chains, CAS transitions, idempotency behavior, and lease ownership
  pass adversarial tests;
- validation, rollback, rollback postcheck, and final status evidence are
  measured and hash-bound;
- crash recovery prevents duplicate actions, inventories orphans, and replays
  terminal state read-only;
- exact authority counters remain zero for auth, credentials, executor, shell,
  subprocess, Kubernetes, cloud, database, production adapter, network,
  online-policy, and production mutation;
- frozen evaluation passes independent review.

## Stop Rules

Stop before implementation or release if any requirement pressures P118 to add
auth, credentials, production mutation, live connectors, online policy writes,
shell/subprocess execution, Kubernetes/cloud/database/network mutation, L4+
authority, free-form action execution, LLM command execution, fail-open policy,
or claims beyond local/mock/sandbox readiness.
