# P138 Local Observation-to-Triage Supervisor Roadmap

## Objective

P138 delivers a production-shaped, local-only, finite supervisor over the
existing P136 incremental observer, the P136-owned fixed-path publisher, and
the P137 bounded triage runtime. It is reconciliation-first: every invocation
reconciles durable P136 publisher, P137, and P138 state before it may start one
new real P136 observation cycle.

P138 coordinates and records durable hashes and statuses. It does not observe
provider artifacts, derive handoff bundles, triage evidence, notify anyone,
take action, remediate, mutate staging or production, or replace an operator.
It is not an unattended production daemon and makes no unbounded-operation
claim.

The qualified release status is exactly
`p138_local_observation_to_triage_supervisor_qualified`.

## Dependency and authority boundary

- P136 alone observes local artifacts. P138 invokes one real
  `observe_one_cycle` only after reconciliation proves that no prior component
  work remains to finish.
- Every real P136 cycle uses one deterministic outcome path for the recoverable
  sequence `p136.cycle_outcome_intent.v1` -> checkpoint replacement ->
  `p136.cycle_completion.v1`. P138 reconciles that path to close both sides of
  the checkpoint boundary before its own phase update.
- `publish_p136_handoff_bundle` remains P136-owned and remains the only writer
  of `handoff/p137/p136_handoff_bundle.v1.json`. Its whole operation is
  serialized by its own nonblocking lease.
- P137 alone validates the fixed bundle and triages it. P138 invokes the
  existing bounded P137 runtime against exact already-validated bundle bytes.
- P138 owns only its supervisor lease, phase, ledger, checkpoint, heartbeat,
  readiness, termination, and release-evidence records.
- Existing P136 and P137 contracts remain authoritative. P138 binds their
  qualified statuses and source hashes but does not re-claim their release
  denominators unless their profiles run separately.

P138 has no authentication, credential, provider, live-connector, network,
DNS, socket, environment-read, subprocess, shell, signal-delivery,
notification/delivery, action/remediation, staging mutation, production
mutation, or operator-replacement authority. Evaluator-only process, signal,
guard, and crash injection does not become runtime authority.

## Reconciliation-first algorithm

Every invocation acquires the P138 supervisor lease before reading coordinated
state. It then validates and reconciles publisher state, current fixed handoff
bytes, the P137 checkpoint and ledger, and the P138 phase and ledger before any
new P136 observation or publication:

1. If publisher state names a current bundle that P137 has not accepted, invoke
   P137 against exactly those bytes. Do not invoke P136 or the publisher.
2. If P137 accepted the current bundle but P138 did not finalize it, validate
   P137 checkpoint, ledger, and classification membership and finalize P138
   without relying on a replay result whose classification is `none`.
3. Only when the current bundle is accepted and the predecessor P138 cycle is
   final may P138 run one real `observe_one_cycle` and select a new promotion
   delta.
4. Same-sequence hash disagreement, a sequence gap, a broken previous hash,
   chain-root disagreement, missing publisher state or current bytes, invalid
   component state, or predecessor mismatch fails closed without P136,
   publication, or P138-ledger advance.

There is no unconditional `P136 -> publish -> P137` execution path. Component
calls are selected only by reconciliation and the durable phase machine.

## Exact phase and ledger contract

The exact phase schema is `p138.supervisor_phase.v1`. Every phase record binds:

- `config_hash`, `cycle_id`, `phase`, `previous_phase_hash`, and
  `previous_p138_ledger_hash`;
- `expected_p136_cycle_id`, `expected_p136_receipt_hash`, and the deterministic
  `p136_cycle_outcome_path`;
- `starting_p136_checkpoint_hash` and `resulting_p136_checkpoint_hash`;
- exact ordered `promotion_sequences` and `promotion_hashes`, including empty;
- `publisher_state_hash`, `bundle_sequence`, and `bundle_hash`;
- `p137_checkpoint_hash`, `p137_ledger_hash`, and sorted
  `classification_hashes`;
- exact `forbidden_authority`, `runtime_activity`, and `evaluator_activity`;
- timestamp and `phase_hash`.

Nullable fields are permitted only before their owning phase. The only normal
monotonic phase path is:

`cycle_started -> p136_completed -> handoff_selected -> handoff_published -> p137_accepted -> cycle_finalized`

An empty promotion delta uses exactly:

`cycle_started -> p136_completed -> cycle_finalized`

and invokes neither publisher nor P137. Each phase is atomically replaced with
file and parent-directory fsync. The finalized ledger is CAS/hash chained to
its predecessor.

| Durable boundary at restart | Required decision |
| --- | --- |
| no phase | Reconcile current publisher/P137 state, then start only if reconciliation permits it. |
| `cycle_started` | Resume the same P136 cycle from its durable intent/checkpoint; never allocate another P138 cycle. |
| `p136_completed` | Rederive and validate the exact stored contiguous delta, then select it. |
| `handoff_selected` | Invoke the serialized publisher once with the stored candidate inputs. |
| `handoff_published` | Validate matching publisher state/current bytes and invoke P137; never call the publisher again. |
| `p137_accepted` | Validate durable P137 checkpoint/ledger/classifications and finalize P138. |
| `cycle_finalized` | Validate ledger membership, clear a retained completed phase, then permit a new observation. |
| any mismatch | Fail closed and preserve the last valid P138 ledger and all component bytes. |

## P136 two-phase cycle outcome

`app/services/p136_incremental_observer.py` and its tests are in P138
implementation scope for the outcome protocol. After promotion records are
durable and **before** checkpoint replacement, every real P136 cycle atomically
writes `p136.cycle_outcome_intent.v1`. The intent contains exactly:

- config hash and deterministic cycle ID;
- consumed index-receipt hash;
- starting checkpoint hash plus the complete canonical resulting checkpoint
  and its hash;
- promotion count and the exact ordered promotion sequence/hash lists,
  including empty;
- outcome creation timestamp;
- file-fsync and parent-directory-fsync assertions;
- intent hash.

P136 then installs that exact checkpoint and replaces the same deterministic
outcome file with `p136.cycle_completion.v1`, preserving the intent bindings
and adding the original intent hash, committed checkpoint hash, completion
timestamp, and completion hash. `cycle_outcome_dir` is an exact relative config
path, disjoint from every other root. `cycle_started` additionally binds the
expected P136 cycle ID, starting checkpoint hash, receipt hash, and
deterministic outcome path.

On restart, P136 reconciles the exact tuple before selecting another receipt:
intent plus starting checkpoint validates every bound promotion byte (or the
exact empty list), installs the bound checkpoint, and completes; intent plus
the bound resulting checkpoint completes; completion plus the bound resulting
checkpoint returns the same cycle; no outcome plus the starting checkpoint
permits the original cycle; every other predecessor, receipt, hash, checkpoint,
or promotion-byte tuple fails closed while preserving the last valid
checkpoint. P138 uses this same-cycle recovery path and never allocates another
receipt or cycle. Crashes on either side of checkpoint replacement consume no
second receipt for nonempty or empty promotion lists.

## Promotion delta and provable bootstrap

Every finalized P138 ledger persists `last_published_promotion_sequence` and
`last_published_promotion_hash`. A new handoff contains exactly the contiguous
promotion records returned by that real P136 cycle, starting at the prior
boundary plus one and ending at
`resulting_checkpoint.next_promotion_sequence - 1`. Every record must match its
canonical P136 entry and the durable resulting checkpoint. An empty delta
suppresses publication and P137. Later cycles never retriage an earlier
promotion sequence.

Bootstrap without a P138 ledger is allowed only when all of these are true:

- publisher state and current fixed bytes validate as genesis with
  `bundle_sequence == 1` and `previous_bundle_hash is None`;
- the bundle promotion sequences equal exactly the contiguous range
  `1..p136_checkpoint.next_promotion_sequence-1`, with no gap, duplicate, or
  omitted checkpoint promotion key;
- the P137 config chain root and any existing P137 checkpoint match that
  genesis.

P138 then records the final genesis sequence/hash as its publication boundary.
A non-genesis current bundle, partial genesis bundle, genesis bundle with
historical checkpoint omissions, or publisher state without exact current
bytes fails closed until a future explicit migration/history contract exists.
P138 never infers history from a later fixed bundle or an unrelated P136
checkpoint.

## Publisher lease and complete split-commit recovery

The P136-owned publisher acquires a nonblocking lease before any publisher
state, intent, or fixed-path read. The lease covers candidate derivation, every
write, recovery, and cleanup. A lease conflict cannot advance sequence, and
every terminal path releases an acquired lease.

Inside that lease, recovery inspects the exact tuple
`(prior state, pending intent, current fixed bytes)` before requiring current
bytes to match prior state:

- old state + old fixed + matching intent: write the intent bundle to fixed,
  write new state, then unlink intent;
- old state + matching intent-bundle fixed: write new state, then unlink
  intent;
- matching new state + matching fixed + stale matching intent: unlink intent;
- no intent + matching state/fixed: perform normal candidate derivation;
- every missing, torn, forked, mismatched, or unbound combination: fail closed
  without deriving a new sequence.

The exact evaluator-only publisher crash boundaries are after intent fsync,
after fixed replacement fsync, and after state replacement fsync before intent
cleanup. Recovery must produce the same sequence/hash exactly once.

## Leases and lock order

All lease paths are exact relative, disjoint, and non-overlapping. The sole lock
order is:

`P138 supervisor lease -> P136 cycle lease (inside observe_one_cycle, released) -> P136 publisher lease (inside publisher, released) -> P137 lease (inside runtime, released) -> P138 final ledger write`

Contention tests cover P138, P136, publisher, and P137 leases plus restart at
each lock boundary. No later lock may be acquired while an earlier component
lease remains held beyond the boundary shown above.

## Exact counter contracts

`forbidden_authority` is exactly the shared P136/P137 15-key tuple below, and
every value is the exact integer zero:

- `provider_call_count`, `live_connector_call_count`, `network_call_count`;
- `dns_lookup_count`, `socket_call_count`, `credential_read_count`;
- `environment_read_count`, `subprocess_launch_count`,
  `shell_execution_count`;
- `signal_count`, `delivery_count`, `remediation_count`;
- `staging_mutation_count`, `production_mutation_count`,
  `operator_replacement_count`.

Import-time and release checks require exact set equality with P136/P137.
Missing or extra keys, booleans, negatives, or nonzero values fail in config,
component results, every phase, termination, each case actual/expected map, and
the rebuilt aggregate. Stale aliases such as authentication, notification, or
action-execution counters are not part of the P138 v1 tuple.

`runtime_activity` is an exact closed nonnegative-integer map with these keys:

- `supervisor_lease_acquire_count`, `supervisor_state_read_count`;
- `phase_write_count`, `ledger_write_count`, `heartbeat_write_count`,
  `readiness_write_count`, `termination_write_count`;
- `reconciliation_count`, `observation_count`, `publication_count`,
  `triage_count`, `recovery_count`, `no_work_count`, `fsync_count`.

`evaluator_activity` is a separate exact closed nonnegative-integer map with
these keys:

- `runner_invocation_count`, `profile_read_count`, `artifact_write_count`;
- `fake_guard_injection_count`, `signal_injection_count`,
  `crash_injection_count`.

Injected callables exist only on evaluator-only test entrypoints. The
production supervisor uses module-owned defaults and rejects arbitrary runtime
callables before invocation. P136/P137 internal activity remains in their own
validated evidence and is not copied into P138 counters.

## Bounded loop, readiness, heartbeat, and resources

- The loop is finite and runs no more than `max_supervisor_cycles`.
- Reconciliation and phase state determine which component, if any, is called;
  finite limits never authorize unconditional component calls.
- Heartbeat and readiness writes follow monotonic cadence. Readiness is local
  evidence only and never triggers delivery or operator handoff.
- SIGINT/SIGTERM handlers set only a stop flag; termination is written at the
  next safe boundary. Signal injection is evaluator activity, while runtime
  `signal_count` remains zero.
- Receipt exhaustion and consecutive-failure threshold use distinct exact stop
  labels and permit no publication after stop.
- Stale readiness/deadman, corrupt state, hash/chain mismatch, lease conflict,
  finite max cycles, and resource exhaustion fail closed with the prior valid
  ledger preserved.
- Default release limits are `wall_limit_ms=30000`, `cpu_limit_ms=15000`, and
  `peak_memory_limit_bytes=134217728`, measured by runner-owned monotonic time,
  `getrusage` self/child CPU, and normalized macOS/Linux RSS growth.

## Exact immutable 30-case matrix

Each case freezes its input hash, expected phase path, expected status/error and
stop reason, exact actual/expected authority/runtime/evaluator maps, resource
limits, and required durable post-state.

| ID | Scenario | Expected terminal/post-state |
| --- | --- | --- |
| P138-CASE-01 | valid bootstrap current bundle | reconcile/finalize; no new publish |
| P138-CASE-02 | new contiguous promotion | observe, one publish, one P137 accept, finalize |
| P138-CASE-03 | zero promotion | finalize no-work; publisher/P137 counts zero |
| P138-CASE-04 | crash after `cycle_started` | restart resumes same cycle |
| P138-CASE-05 | crash after `p136_completed` | same delta published once |
| P138-CASE-06 | crash after `handoff_selected` | publisher invoked once on recovery |
| P138-CASE-07 | publisher crash after intent | publisher recovers same sequence |
| P138-CASE-08 | crash after `handoff_published` | current bytes consumed; no republish |
| P138-CASE-09 | crash after P137 commit | validate membership and finalize without replay label |
| P138-CASE-10 | P137 lease conflict then restart | sequence N retained/accepted before N+1 exists |
| P138-CASE-11 | same-sequence bundle fork | fail closed, prior P138 ledger preserved |
| P138-CASE-12 | sequence gap/previous-hash break | fail closed, no observation/publish |
| P138-CASE-13 | publisher state/fixed-byte mismatch | fail closed, no component calls |
| P138-CASE-14 | P138 lease contention | zero component calls/writes |
| P138-CASE-15 | P136 lease contention | no publisher/P137/P138-final advance |
| P138-CASE-16 | publisher lease contention | no sequence/P137/P138-final advance |
| P138-CASE-17 | P137 stale readiness/version | fail closed with current bundle retained |
| P138-CASE-18 | later delta after prior accepted | only new promotion atoms/classifications appear |
| P138-CASE-19 | SIGINT/SIGTERM safe boundary | evaluator signal only; hash-bound termination |
| P138-CASE-20 | forbidden-callable/secret/path/resource guard | blocked before runtime authority |
| P138-CASE-21 | P136 checkpoint committed with promotions before P138 phase write | completion record advances same cycle; no extra receipt |
| P138-CASE-22 | P136 checkpoint committed empty before P138 phase write | empty completion finalizes no-work; no extra receipt/publish |
| P138-CASE-23 | publisher crash after fixed replacement | same intent bundle/state recovered; same sequence once |
| P138-CASE-24 | publisher crash after state replacement | stale intent unlinked; same sequence once |
| P138-CASE-25 | partial genesis and non-genesis bootstrap without history | both fail closed before observation |
| P138-CASE-26 | P136 receipt exhaustion and consecutive-failure threshold | exact distinct stop labels; no publish after stop |
| P138-CASE-27 | finite max-cycle and heartbeat cadence | exact cycle count and heartbeat/readiness writes |
| P138-CASE-28 | stale readiness/deadman plus safe signal boundary | exact stop/termination evidence and evaluator-only signal |
| P138-CASE-29 | promotion cycle crashes after outcome-intent fsync before checkpoint | P136 installs bound checkpoint, writes completion, P138 publishes once; no extra receipt |
| P138-CASE-30 | empty cycle crashes after outcome-intent fsync before checkpoint | P136 installs bound empty checkpoint, writes completion, P138 no-work finalizes; no extra receipt/publish |

CASE-01 through CASE-20 retain the amended plan meanings; CASE-07 is
specifically the crash after publisher intent fsync. CASE-21 through CASE-25
use real durable component boundaries. At minimum CASE-02, CASE-03, CASE-07,
CASE-09, CASE-10, CASE-16, CASE-18, CASE-29, and CASE-30 also use real P136,
publisher, and/or P137 boundaries rather than callback-only spies. CASE-21 and
CASE-22 exercise the outcome-intent state after checkpoint replacement and
before completion replacement; CASE-29 and CASE-30 exercise it before
checkpoint replacement. The runner, profile, totals, freeze manifest, final
review, and `p138-release` all require exactly 30 expected, 30 passed, and 0
failed.

## Frozen release evidence and matching paths

Preliminary and final modes use the same tracked output paths:

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev python scripts/run_p138_observation_triage_supervisor.py --mode preliminary --output-dir evals/p138/output
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev python scripts/run_p138_observation_triage_supervisor.py --mode final --canonical-matrix evals/p138/output/canonical-matrix.json --freeze-manifest evals/p138/output/freeze-manifest.json --final-implementation-review evals/p138/final-implementation-review.json --output-dir evals/p138/output
```

The tracked release artifacts are exactly:

- `evals/p138/output/canonical-matrix.json`;
- `evals/p138/output/freeze-manifest.json`;
- `evals/p138/output/release-evidence.json`;
- `evals/p138/final-implementation-review.json`.

The freeze manifest and independent final review bind the complete transitive
P136 two-phase cycle-outcome implementation, publisher
serialization/recovery, P137, and P138 runtime/contracts/release validators,
runner, fixtures, profile, matrix, and tests. Preliminary mode creates the
review inputs at the tracked paths. Final mode runs only after the independent
review exists, regenerates no reviewed input, and fails on any hash drift.
`p138-release` consumes these exact tracked paths, validates 30/30 and rebuilt
exact counters, and is followed by separate `p136-release`, `p137-release`,
docs, full verification, authority/leak scans, and `git diff --check`.

## Ticket ownership and stop rules

- P138-001: exact contracts, paths, phase/two-phase-outcome schemas, and
  counters.
- P138-002: reconciliation-first algorithm, phase machine, P136 two-phase
  cycle-outcome integration, and contiguous-delta selection.
- P138-003: publisher whole-operation lease, split-commit recovery, lock order,
  crash recovery, and bounded loop state.
- P138-004: delta/zero-work, bootstrap, authority, callable, and leak guards.
- P138-005: exact 30-case real-boundary fixtures, runner, and profile.
- P138-006: frozen release evidence and `p138-release` profile.
- P138-007: documentation and no-authority/operator boundary.
- P138-008: independent frozen-source review and reproducible release handoff.

Stop implementation if P138 would require authentication, credentials,
environment reads, provider/live-connector APIs, network/DNS/socket access,
notification/delivery, action/remediation, subprocess/shell runtime authority,
staging/production mutation, operator replacement, or P136/P137 contract
weakening. Stop release on any nonzero forbidden-authority value, exact-key
mismatch, frozen-source drift, matrix result other than 30/30, unreproducible
tracked input, missing independent final implementation review, or unresolved
P0/P1/P2 final-review finding. This roadmap defines the qualification contract;
it is not itself evidence that final qualification exists.
