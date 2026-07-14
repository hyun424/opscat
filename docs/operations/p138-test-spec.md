# P138 Local Observation-to-Triage Supervisor Test Specification

## Contract, path, and authority validation

- Validate exact-key, canonical, self-hashed P138 config, phase, ledger,
  checkpoint, heartbeat, readiness, termination, resource, case-evidence, and
  release-evidence records.
- Validate `p138.supervisor_phase.v1`, `p136.cycle_outcome_intent.v1`, and
  `p136.cycle_completion.v1` with the exact fields and ownership described by
  the roadmap.
- Reject missing/unknown keys, invalid hashes or timestamps, booleans in integer
  fields, negatives, unbounded limits, stamped measurements, and nullable phase
  fields after their owning phase.
- Require relative, exact, disjoint, non-overlapping P138, P136 cycle-outcome,
  publisher state/intent/lease, fixed-handoff, and P137 state paths. Reject
  absolute, escaping, symlink-parent, or overlapping paths.
- Require `p136_handoff_bundle_path` exactly
  `handoff/p137/p136_handoff_bundle.v1.json`.
- Require complete canonical P136 and P137 inputs and evidence, with matching
  hashes and statuses `p136_incremental_local_observation_qualified` and
  `p137_local_evidence_triage_qualified`. Hash-only references fail closed.
- Require exact set equality for the shared 15-key `forbidden_authority` tuple:
  `provider_call_count`, `live_connector_call_count`, `network_call_count`,
  `dns_lookup_count`, `socket_call_count`, `credential_read_count`,
  `environment_read_count`, `subprocess_launch_count`,
  `shell_execution_count`, `signal_count`, `delivery_count`,
  `remediation_count`, `staging_mutation_count`,
  `production_mutation_count`, and `operator_replacement_count`.
- Require every forbidden-authority value to be integer zero in config,
  dependency result validation, every phase, termination, every case
  actual/expected map, aggregate evidence, and final release evidence. Reject
  stale authentication/notification/action-execution aliases as extra keys.
- Require exact set equality and nonnegative integers for `runtime_activity`:
  `supervisor_lease_acquire_count`, `supervisor_state_read_count`,
  `phase_write_count`, `ledger_write_count`, `heartbeat_write_count`,
  `readiness_write_count`, `termination_write_count`,
  `reconciliation_count`, `observation_count`, `publication_count`,
  `triage_count`, `recovery_count`, `no_work_count`, and `fsync_count`.
- Require exact set equality and nonnegative integers for
  `evaluator_activity`: `runner_invocation_count`, `profile_read_count`,
  `artifact_write_count`, `fake_guard_injection_count`,
  `signal_injection_count`, and `crash_injection_count`.

## Reconciliation-first behavior

- Acquire the nonblocking P138 lease before reading any coordinated P138,
  publisher, or P137 state. A competitor performs zero component calls and
  writes.
- With no durable phase, reconcile current publisher state/fixed bytes, P137
  checkpoint/ledger, and P138 ledger before permitting observation.
- If a current publisher bundle is not accepted by P137, call P137 with exactly
  those bytes and assert zero P136 and publisher calls.
- If P137 durably accepted the current bundle but P138 did not finalize it,
  validate P137 checkpoint, ledger, and classification membership and finalize
  without relying on replay `classification="none"`.
- Permit one real `observe_one_cycle` only after the current bundle is accepted
  and the predecessor P138 cycle is final.
- Same-sequence fork, sequence gap, broken previous hash, chain-root mismatch,
  missing publisher state/current bytes, invalid component state, and
  predecessor mismatch all fail closed with zero new observation, publication,
  and ledger advance.

Tests must not assert an unconditional component order. For the new-promotion
path only, the expected phase-selected calls are one P136 observation, one
serialized publication, and one P137 acceptance. Reconciliation and recovery
paths may legitimately call only one component or none.

## Exact phase-machine tests

- Accept only
  `cycle_started -> p136_completed -> handoff_selected -> handoff_published -> p137_accepted -> cycle_finalized`.
- Accept only
  `cycle_started -> p136_completed -> cycle_finalized` for empty deltas and
  assert zero publisher and P137 calls.
- For every phase, validate `config_hash`, `cycle_id`, `phase`,
  `previous_phase_hash`, `previous_p138_ledger_hash`, both P136 checkpoint
  hashes, publisher state/bundle fields, P137 checkpoint/ledger/classification
  fields, exact three counter maps, timestamp, and `phase_hash`.
- Assert file fsync and parent-directory fsync after each atomic phase
  replacement and CAS/hash chaining for the final ledger.
- Restart from each durable boundary and assert the exact roadmap recovery
  decision: same cycle at `cycle_started`, stored delta at `p136_completed`,
  one publisher call at `handoff_selected`, no republish at
  `handoff_published`, membership-based finalization at `p137_accepted`, and
  ledger validation before clearing `cycle_finalized`.
- On any mismatch, preserve the last valid P138 ledger and all component bytes.

## P136 two-phase cycle-outcome boundary

- Require every real P136 cycle, including an empty one, to use the exact
  durable order `p136.cycle_outcome_intent.v1` -> checkpoint replacement ->
  `p136.cycle_completion.v1` at one deterministic outcome path.
- Write the outcome intent only after every bound promotion record is durable
  and before replacing the checkpoint. Validate its exact common fields:
  config hash, deterministic cycle ID, index-read receipt hash, starting
  checkpoint hash, complete canonical resulting checkpoint and hash, promotion
  count, exact ordered promotion sequences/hashes including empty, creation
  timestamp, file/parent fsync assertions, and intent hash.
- Replace the checkpoint only with the exact resulting checkpoint bound by the
  intent. Then replace that same outcome file with completion before return.
  Completion preserves every common field and adds the original intent hash,
  committed checkpoint hash, completion timestamp, and completion hash.
- Validate exact relative `cycle_outcome_dir`, its byte budget, its deterministic
  per-cycle path, and disjointness from all other roots.
- Require `cycle_started` to bind expected P136 cycle ID, starting checkpoint
  hash, receipt hash, and deterministic outcome path.
- Under the P136 lease and before selecting another receipt, accept only these
  recovery tuples: intent + starting checkpoint validates exact promotion bytes
  (or exact empty), installs the bound checkpoint, and completes; intent +
  bound resulting checkpoint completes; completion + bound resulting
  checkpoint returns/reconciles that cycle; no outcome + starting checkpoint
  permits the original observation. Every other predecessor, receipt, hash,
  checkpoint, outcome, or promotion-byte tuple fails closed and preserves the
  last valid checkpoint.
- P138 `cycle_started` reconciliation must use that same-cycle recovery result,
  advance to `p136_completed`, and never allocate a new receipt or cycle.
- CASE-21 and CASE-22 inject death after checkpoint replacement and before
  completion replacement for nonempty and empty results. CASE-29 and CASE-30
  inject death after outcome-intent fsync and before checkpoint replacement.
  Across all four cases assert no second index read or receipt, exactly-once
  publication for nonempty results, and zero publisher/P137 calls for empty
  results.

## Delta and genesis-only bootstrap

- Validate persisted `last_published_promotion_sequence` and
  `last_published_promotion_hash` in each finalized P138 ledger.
- Require a new handoff delta to contain exactly the ordered contiguous P136
  promotion records from the prior boundary plus one through
  `resulting_checkpoint.next_promotion_sequence - 1`.
- Validate every delta record against its canonical P136 entry and resulting
  checkpoint. Reject gaps, duplicates, omitted keys, reordered records, stale
  records, and hashes not present in the real cycle result.
- Empty delta records `no_work_count` and suppresses publisher/P137 calls.
- Without a P138 ledger, allow bootstrap only for matching publisher
  state/current fixed bytes whose bundle is genesis with
  `bundle_sequence == 1`, `previous_bundle_hash is None`, and exact promotion
  sequence range `1..p136_checkpoint.next_promotion_sequence-1`.
- Require the P137 config chain root and any P137 checkpoint to match that
  genesis, then establish the final genesis sequence/hash as the P138 boundary.
- Reject non-genesis current bundles, partial genesis, genesis with checkpoint
  history omissions, publisher state without exact fixed bytes, and unrelated
  pre-existing P136 checkpoints before any observation.

## Publisher whole-operation lease and split-commit recovery

- Acquire the publisher's nonblocking lease before reading publisher state,
  intent, or fixed bytes. Cover candidate derivation, all writes, recovery, and
  cleanup. A competitor reads/writes nothing and cannot advance sequence.
- Under the lease, inspect `(prior state, pending intent, current fixed bytes)`
  in this order and assert exactly:
  - old state + old fixed + matching intent writes the intent bundle to fixed,
    writes new state, then unlinks intent;
  - old state + matching intent-bundle fixed writes new state, then unlinks
    intent;
  - matching new state + matching fixed + stale matching intent only unlinks
    intent;
  - no intent + matching state/fixed performs normal candidate derivation;
  - every missing, torn, forked, mismatched, or unbound tuple fails closed
    without deriving a sequence.
- Inject crashes after intent fsync, after fixed replacement fsync, and after
  state replacement fsync before intent cleanup. Assert restart recovers the
  same bundle hash and sequence exactly once.
- Assert every terminal path releases an acquired publisher lease.

## Lease order, bounded loop, readiness, and signals

- Enforce the sole order:
  `P138 supervisor lease -> P136 cycle lease (released inside observe_one_cycle) -> P136 publisher lease (released inside publisher) -> P137 lease (released inside runtime) -> P138 final ledger write`.
- Cover P138, P136, publisher, and P137 contention plus crash/restart at each
  lock boundary. Assert no lock inversion or component advance past a conflict.
- Run at most `max_supervisor_cycles` with monotonic cadence. Assert exact cycle
  count and exact heartbeat/readiness writes.
- Receipt exhaustion and consecutive-failure threshold emit distinct exact stop
  labels and perform no publication after stop.
- Stale readiness/deadman stops before component work and writes exact local
  stop/termination evidence.
- SIGINT/SIGTERM injection sets only a stop flag and writes termination at the
  next safe boundary. Increment evaluator `signal_injection_count`; keep runtime
  forbidden `signal_count` zero.
- Corrupt state, resource exhaustion, lease conflict, and finite-cycle stop
  preserve the prior valid ledger and never widen authority.

## Static, runtime, and leak guards

- Static scans reject P138 authentication, credential/environment access,
  provider/live-connector, network/DNS/socket, subprocess/shell,
  signal-delivery, notification/delivery, action/remediation,
  staging/production mutation, and operator-replacement surfaces.
- Allow only the named P136 observer, P136-owned publisher, and P137 runtime
  component boundaries plus their required contracts and validators.
- Accept injected callables only through evaluator-only entrypoints. The
  production supervisor uses module-owned defaults and rejects arbitrary
  callables before invocation.
- Assert fake-guard and crash probes increment only evaluator activity and leave
  every forbidden-authority value at exact zero.
- Reject promoted absolute paths, secrets/tokens, endpoints, raw provider
  payloads, prompt-injection text, shell commands, delivery targets,
  action/remediation instructions, and staging/production targets.
- Assert P138 performs zero original provider-artifact opens/reads and makes no
  new provider-authenticity claim.

## Resources and independent counter reconstruction

- Measure wall time with runner-owned monotonic time; self and child CPU with
  `resource.getrusage`; and normalized macOS/Linux peak RSS growth in bytes.
- Enforce default `wall_limit_ms=30000`, `cpu_limit_ms=15000`, and
  `peak_memory_limit_bytes=134217728`.
- Rebuild every case's phase path, component calls, exact authority/runtime/
  evaluator maps, post-state, and resource values from frozen case evidence.
- Reject fixed assumed-zero summaries, stamped resource values, inconsistent
  deltas, aliases, unknown keys, booleans, negatives, and any aggregate not
  equal to the sum of its case evidence.
- Keep P136/P137 internal activity in their own validated evidence.

## Exact immutable 30-case runner

The runner executes exactly the 30 roadmap rows with IDs
`P138-CASE-01` through `P138-CASE-30` and retains their exact scenario and
terminal/post-state meanings. CASE-07 is specifically the publisher crash after
intent fsync.

Required release evidence includes:

- exactly 30 expected, 30 passed, and 0 failed;
- frozen input hash, expected phase path, status/error, stop reason, exact
  actual/expected authority/runtime/evaluator maps, resources, and durable
  post-state for every row;
- real durable P136/publisher/P137 boundaries for CASE-21 through CASE-25 and
  CASE-29 through CASE-30;
- real applicable component boundaries, rather than callback-only spies, for
  at least CASE-02, CASE-03, CASE-07, CASE-09, CASE-10, CASE-16, and CASE-18;
- exact coverage of reconciliation, empty delta, all phase crashes, all three
  publisher split-commit crash boundaries, both sides of the P136
  outcome/checkpoint commit, four lease-contention surfaces,
  fork/chain/state mismatch, genesis rejection, P136 two-phase outcome recovery,
  stop labels, cadence/readiness/signals, and authority/leak/resource guards;
- no duplicated or re-claimed P136/P137 canonical denominator.

The runner, source-bound profile, freeze manifest, final review, release
evidence, and `p138-release` all fail unless the exact 30/30 denominator and
exact rebuilt counters agree.

## Frozen release flow and exact paths

Preliminary and final use the same tracked output directory and exact commands:

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev python scripts/run_p138_observation_triage_supervisor.py --mode preliminary --output-dir evals/p138/output
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev python scripts/run_p138_observation_triage_supervisor.py --mode final --canonical-matrix evals/p138/output/canonical-matrix.json --freeze-manifest evals/p138/output/freeze-manifest.json --final-implementation-review evals/p138/final-implementation-review.json --output-dir evals/p138/output
```

- Preliminary mode writes
  `evals/p138/output/canonical-matrix.json`,
  `evals/p138/output/freeze-manifest.json`, and preliminary
  `evals/p138/output/release-evidence.json`.
- Freeze the complete transitive P136 two-phase cycle-outcome implementation,
  publisher, P137, and P138 runtime/contracts/release validators, runner,
  fixtures, profile, matrix, cases, and tests.
- Final mode consumes the exact tracked matrix and manifest plus
  `evals/p138/final-implementation-review.json`; it regenerates and overwrites
  no reviewed input.
- Require an independent frozen-source review with zero unresolved P0/P1/P2
  findings and reject any bound hash drift.
- Runner stdout contains exact `release_status`, `mode`, and `evidence_hash`.
- `p138-release` consumes the exact same tracked paths and independently
  validates 30/30, counter maps, resources, source bindings, final review, and
  exact status `p138_local_observation_to_triage_supervisor_qualified`.

## Verification sequence

1. Lock the roadmap, this test spec, ticket README, and eight ticket contracts.
2. P138-001: observe failing exact schema/path/counter tests, implement, and run
   targeted pytest, Ruff, and Mypy.
3. P138-002: observe failing reconciliation/phase/two-phase-outcome/delta
   tests, implement, and run targeted checks including P136 tests.
4. P138-003: observe failing publisher lease/split-commit/lock-order/recovery/
   loop tests, implement, and run targeted checks including publisher tests.
5. P138-004: observe failing zero-work/bootstrap/authority/callable/leak tests,
   implement, and run targeted checks.
6. P138-005: observe failing exact 30-case real-boundary runner/profile tests,
   implement, and run targeted checks.
7. P138-006: observe failing freeze/evidence/profile tests, then wire
   `p138-release` only after the runner and targeted tests are stable.
8. P138-007: complete documentation and no-authority/operator-boundary checks.
9. Run preliminary mode to the exact tracked output paths and freeze the bound
   source/profile/fixture/case/matrix inputs.
10. P138-008: complete the independent frozen-source review, then run final mode
    against the exact tracked inputs without regeneration.
11. Run `UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p138-release`.
12. Run separate `p136-release` and `p137-release` profiles; P138 evidence binds
    their results but does not silently re-claim their denominators.
13. Run docs and full profiles, authority/leak/secret/path checks, and
    `git diff --check`.

Do not start a dependent ticket before its predecessor's targeted evidence is
green. Do not release on any nonzero authority value, counter-key mismatch,
hash drift, result other than 30/30, regenerated reviewed input, unresolved
P0/P1/P2 finding, or authority beyond the local no-action boundary.
