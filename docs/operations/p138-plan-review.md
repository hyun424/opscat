# P138 Independent Plan Review

Review date: 2026-07-14
Repository commit: `1da71a08946d42ab4453918f6737a27901bab3e5`
Reviewed plan SHA-256: `a8643d6e4032a85f26fe4a0e75b3a710ff2871c8172d32d0c94ce9149318785b`

## Verdict

**REJECT**

Finding count: P0=1, P1=5, P2=0, P3=0.

The proposed thin-composition boundary is appropriate, but the plan is not
implementation-ready. Its normal cycle can overwrite an unconsumed fixed-path
handoff after a P137 lease conflict, creating a sequence gap that current P137
correctly rejects. The restart, delta-publication, lease, exact-zero-authority,
and verification contracts are also not precise enough to prove recovery or
release qualification.

## Prioritized Findings

### P0 — The planned cycle can irreversibly skip an unconsumed fixed handoff

The plan specifies the unconditional order `P136 -> publish -> P137` for each
supervisor cycle and includes P137 lease conflict as a matrix case, but it does
not require reconciliation of an already-published bundle before another P136
run or publish (`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:90-102`,
`:158-170`).

Current source makes this unsafe:

- Every successful publisher invocation derives `last_bundle_sequence + 1` and
  atomically replaces the sole fixed handoff path
  (`app/services/p137_p136_handoff.py:90-153`, `:238-301`). The current test
  explicitly republishes the same P136 checkpoint and receives sequence 2
  (`tests/test_p137_p136_handoff.py:189-222`).
- A P137 lease conflict returns before reading state or handoff bytes
  (`app/services/p137_runtime.py:93-105`), as asserted by
  `tests/test_p137_runtime.py:275-299`.
- With no P137 checkpoint, only sequence 1 is accepted. With a checkpoint, only
  the same hash/sequence or the exact next sequence chained to the last hash is
  accepted (`app/services/p137_runtime.py:856-880`; the validator independently
  enforces the same rule in `app/services/p137_p136_handoff.py:589-607`).

Therefore: publish sequence 1 -> P137 lease conflict -> next supervisor cycle
publishes sequence 2 over the fixed path -> P137 still has no checkpoint and
rejects sequence 2 as `handoff_genesis_sequence_invalid`. The plan has no
retained sequence-1 path or rollback mechanism.

**Mandatory correction:** make recovery/reconciliation the first operation
under the P138 lease, before P136 is invoked. Compare the validated publisher
state/current fixed bundle with the validated P137 checkpoint:

1. If P137 has not accepted the current publisher bundle, invoke P137 against
   exactly those current bytes; do not invoke P136 or publish a new bundle.
2. Only after P137 acceptance and P138 cycle-ledger finalization may P136 run and
   a new sequence be published.
3. Same-sequence hash disagreement, a gap, a broken previous hash, missing
   publisher state/current bytes, or an unexpected chain root must fail closed
   without any new publish.
4. Add a real two-invocation test: sequence 1 publish -> P137 lease conflict ->
   restart -> sequence 1 accepted -> only then may sequence 2 be created.

### P1 — Restart reconciliation is stated, not specified as an executable state machine

The plan names cycle, handoff, and triage intents and four crash points, but it
does not define their exact fields, predecessor bindings, phase transitions, or
recovery decisions (`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:111-123`).
The acceptance phrase “recovers idempotently or fails closed” permits a valid,
fully committed phase to be abandoned and does not distinguish inconsistency
from an ordinary restart.

Current component behavior requires explicit reconciliation:

- The P136 foreground API returns only the final checkpoint, termination
  receipt, and completed-cycle count (`app/services/p136_runner.py:303-308`,
  `app/services/p136_incremental_observer.py:1147-1198`).
- Publisher recovery is idempotent only while its own exact pending intent
  exists. After a completed publish, another call creates the next sequence
  (`app/services/p137_p136_handoff.py:90-153`,
  `tests/test_p137_p136_handoff.py:225-262`).
- Replaying an already accepted bundle returns `reused_bundle` with
  classification `none`, not the original cycle result
  (`app/services/p137_runtime.py:194-213`,
  `tests/test_p137_runtime.py:483-519`).

**Mandatory correction:** define a hash-chained P138 phase machine with exact
records for at least `cycle_started`, `p136_completed`, `handoff_selected`,
`handoff_published`, `p137_accepted`, and `cycle_finalized`. Bind each record to
the P138 config hash, predecessor P138 ledger hash, starting and resulting P136
checkpoint hashes, publisher state hash, bundle sequence/hash, P137 checkpoint
and ledger hashes, classification hashes, and exact authority maps. Specify a
recovery table:

- intent only: resume/reconcile the same P136 cycle from durable P136 state;
- P136 complete: derive the same bounded promotion delta and publish once;
- publisher committed: recognize the matching publisher state/current bytes and
  consume them without calling the publisher again;
- P137 committed: validate P137 checkpoint/ledger/classification membership and
  finalize P138 without relying on replay's `classification="none"`;
- any hash, predecessor, phase, or byte mismatch: fail closed and preserve the
  last valid P138 ledger.

Known valid crash windows must reconcile deterministically; fail-closed is the
outcome for inconsistent evidence, not an interchangeable success criterion.

### P1 — The plan has no exact “new promotions only” handoff contract

The plan says to publish from durable P136 checkpoint/promotion state but does
not define which promotions belong to a P138 cycle or how an empty observation
delta is represented (`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:90-102`,
`:314-315`). Passing every durable `checkpoint.promotion_keys` value on each
cycle would retriage historical evidence.

The current handoff validator checks every supplied promotion against checkpoint
membership, but does not require the supplied map to equal the whole checkpoint
map (`app/services/p137_p136_handoff.py:173-209`). The publisher accepts the
caller-supplied promotion sequence and creates a new bundle sequence every time
(`app/services/p137_p136_handoff.py:238-301`, `:472-494`). P137 treats only the
same bundle sequence/hash as reuse; an exact next sequence is new work
(`app/services/p137_runtime.py:856-880`).

**Mandatory correction:** define and persist the last-published P136 promotion
sequence/hash boundary. A new handoff must contain exactly the contiguous,
previously unpublished promotion records, each validated against the returned
durable checkpoint. A successful P136 cycle with zero new promotions must not
advance the publisher or invoke P137. Define bootstrap behavior for an existing
P136 checkpoint with no P138 ledger, and add tests proving that old atoms and
classifications are not retriaged when a later promotion arrives.

### P1 — The lease contract does not serialize all writers or define lock ordering

The proposed P138 lease prevents competing P138 instances, but the plan does not
state its relationship to existing component locks or the lock-free publisher
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:90-95`, `:111-123`).

- P136 acquires its lease inside each `observe_one_cycle` call, so it is not held
  across foreground-loop completion, snapshot selection, and handoff publication
  (`app/services/p136_incremental_observer.py:487-506`, `:1147-1198`).
- P137 acquires its own nonblocking lease before state/handoff reads
  (`app/services/p137_runtime.py:93-106`).
- `publish_p136_handoff_bundle` has no lease or write-time CAS around its
  read/derive/intent/fixed-path/state sequence
  (`app/services/p137_p136_handoff.py:71-153`). A P138-only lease cannot serialize
  a direct concurrent publisher caller.

**Mandatory correction:** specify disjoint lease paths, one lock order, and
release behavior on every terminal path. Either extend the P136-owned publisher
with a nonblocking publisher lease/CAS, which requires adding that existing file
to the authorized change scope, or provide an equivalently enforced sole-writer
contract. Test P138 contention, P136 lease contention, P137 lease contention,
publisher contention, and crash/restart while each lock is held. No component
lease conflict may advance the publisher sequence or P138 phase ledger.

### P1 — Exact-zero authority is directionally correct but not an exact P138 contract

The plan says “union of P136/P137 forbidden surfaces plus supervisor-only
counters” without enumerating the versioned P138 keys, defining ownership, or
defining how actual and expected per-phase/per-case values are rebuilt
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:68-78`, `:133-143`,
`:188-197`). “Zero side effects” is also inaccurate because P138 intentionally
writes local state; the invariant is zero forbidden external authority with
measured nonzero local runtime activity.

P136 and P137 currently expose the same exact 15 forbidden keys
(`app/services/p136_incremental_observer.py:53-69`,
`app/services/p137_contracts.py:153-169`). P137's release validator requires
exact per-case actual and expected maps, exact-zero values, rebuilt aggregates,
and actual/expected equality (`app/services/p137_release_evidence.py:190-205`,
`:236-288`). P138 must preserve at least that rigor.

**Mandatory correction:** freeze the P138 v1 forbidden-authority key set
explicitly (or prove exact equality to the versioned P136/P137 sets at import
and release validation), including any genuinely new supervisor surface. Require
`type(value) is int and value == 0`, with missing, extra, boolean, negative, or
nonzero values rejected in config, every component result, every phase record,
termination, every release case, expected maps, and rebuilt totals. Keep fake
guard calls and delivered signals exclusively in exact evaluator-activity maps.
Define how injected test callables are distinguished from production defaults;
an arbitrary callable cannot both be accepted for execution and proven to have
zero authority merely from its returned counters.

### P1 — Verification is not reproducible or complete enough for the claimed gate

The release denominator is “around 12-16 cases,” not an exact immutable matrix,
and several bullets combine multiple materially different outcomes
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:145-170`). This
cannot support the promised exact totals and frozen case hashes. The listed
preliminary command writes to `/tmp/opscat-p138-preliminary`, while the next
final command consumes `evals/p138/output/canonical-matrix.json` and
`freeze-manifest.json`; no listed command creates those consumed paths
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:273-283`).

The matrix also lacks mandatory end-to-end cases for the P0 sequence-loss
scenario, recovery after P137 commit but before P138 finalization, publisher
state/fixed-byte/P137-checkpoint disagreement, zero-promotion suppression,
promotion-delta continuity, and concurrent publisher serialization.

**Mandatory correction:** replace the approximate denominator with exact case
IDs, inputs, expected phase transitions, expected stop/error labels, exact
runtime/evaluator/authority maps, and required durable post-state. Make the
preliminary output paths exactly match final inputs (or pass the preliminary
paths directly). Require real-component integration tests in addition to
injected call-order tests. Bind the complete transitive P136/P137/P138 runtime,
contracts, release validators, runner, fixtures, profile, matrix, and tests in
the freeze manifest and final independent review. The `p138-release` profile
must reproduce final evidence from those frozen inputs and fail on any reviewed
hash change.

## Required Area Assessment

| Area | Assessment | Approval condition |
| --- | --- | --- |
| Restart reconciliation | **INSUFFICIENT** | Exact phase records, predecessor/hash bindings, and a deterministic recovery table for every committed boundary. |
| Fixed handoff sequencing | **UNSAFE** | Reconcile/consume the current bundle before any new observation or publication; prove lease-conflict recovery without a sequence gap. |
| Leases | **INSUFFICIENT** | Enforced publisher serialization, disjoint paths, explicit lock order, and contention/crash tests across P138/P136/publisher/P137. |
| Exact-zero authority | **INCOMPLETE** | Versioned exact keys plus per-phase/per-case actual and expected maps, strict zero/type validation, aggregate rebuild, and evaluator separation. |
| Verification sufficiency | **INSUFFICIENT** | Exact frozen denominator, corrected artifact flow, real integration/restart/contention cases, transitive source binding, and reproducible release profile. |

## Validation Evidence

The current component baseline was exercised with:

```text
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q \
  tests/test_p136_runner.py \
  tests/test_p137_p136_handoff.py \
  tests/test_p137_runtime.py \
  tests/test_p137_authority_boundary.py
```

Result: exit 0; all collected tests passed, with one existing Starlette/httpx
deprecation warning. This confirms the current component semantics cited above;
it does not validate the absent P138 reconciliation layer.

Reviewed source hashes:

```text
f1c8db4036416c8163edb4534025941022d4f7d10aed2452a5805ee1c32fcbe8  app/services/p136_runner.py
1ee59e336dec58b11351e593e1a2abee76d208722397d066fad99e297440c8de  app/services/p136_incremental_observer.py
d1074cbc8c47d25299fb3644324f82f61760ff14c422d03f066ce741225a1b29  app/services/p137_p136_handoff.py
2844b4acac1ab28f138e4398ca417a8ec1f91ed02e36e974c87b4300b0184f35  app/services/p137_runtime.py
43ff53f592fa2e3665328b6be7fa3a787ed05ef918fb4e621abb389b7c95fdc8  app/services/p137_contracts.py
b2d4561f04f7566149b9a9a077314a6fc823283888565ff30b94e74ae7947a5f  app/services/p137_release_evidence.py
a153019450416b7b090d5c6a8b960eb603a57ce4ad67e13d433c444850482a03  tests/test_p136_runner.py
92939cf0f34754b8ebb3d4691676c1ed57a50233b76ad5abc2f37905c2319cfb  tests/test_p137_p136_handoff.py
616c022b9cb71d9d55d29e533c35018cf513c28fef771a4fb658249f1d4f83f9  tests/test_p137_runtime.py
e8757b53d1e6ad180cdb8e76557e3d1bfcde4eb2d3d529b63ce6dc541349cac5  tests/test_p137_authority_boundary.py
90d9014aa9222bf89630cf8453852906b4b5af7b12136beae324ef2a5c85b923  scripts/verify.sh
```

## Re-review Gate

Re-review only after all six mandatory corrections are incorporated into the
plan with exact owning files and tests. Approval requires P0=0 and P1=0; no P138
implementation or release claim should proceed from the current plan.

---

## Re-review — Amended Plan

Re-review date: 2026-07-14
Repository commit: `1da71a08946d42ab4453918f6737a27901bab3e5`
Amended plan SHA-256: `576dff2d7086418b816d8984315b3552b2d1440cccf05d65f50aaa5468788d13`

### Definitive Verdict

**REJECT**

Finding count: P0=0, P1=3, P2=1, P3=0.

The amendment closes the original P0 sequence-loss scenario: reconciliation now
precedes observation/publication, an unaccepted fixed bundle must be consumed
before sequence N+1 can exist, and the exact P137-lease-conflict restart is in
the frozen matrix. It also makes the lease order and exact-zero authority
contracts implementation-ready.

Approval still fails because P1 is not zero. Current P136 and publisher commit
ordering exposes two ordinary crash windows that the amended phase table cannot
deterministically reconcile, and the proposed no-ledger bootstrap cannot prove
its last-published promotion boundary from the evidence current P136/P137 retain.
The exact release matrix consequently does not exercise all required durable
states.

### Mandatory Correction Readiness

| Mandatory correction | Re-review status | Source-bound conclusion |
| --- | --- | --- |
| Reconciliation before new observation/publication | **READY** | Plan lines 346-361 require exact-current-bundle consumption or fail-closed reconciliation before P136/publisher calls, matching P137's exact next-sequence rule at `app/services/p137_runtime.py:856-880`. |
| Executable hash-chained phase/restart machine | **NOT READY** | The phase table does not distinguish P136 commit before `p136_completed`, and publisher recovery covers intent-first failure but not later split commits. See P1 findings 1 and 2. |
| Exact new-promotions-only delta and bootstrap | **NOT READY** | Steady-state delta bounds are exact, but the no-P138-ledger bootstrap boundary is not derivable for a later or partial current bundle. See P1 finding 3. |
| Enforced leases and lock order | **READY** | Plan lines 404-415 authorize the existing publisher file, require a nonblocking whole-operation publisher lease, enumerate one lock order, and cover contention. |
| Exact-zero authority/evaluator separation | **READY** | Plan lines 417-434 freeze the same 15 keys as `app/services/p137_contracts.py:153-169`, reject booleans/nonzero/shape drift at every layer, and prohibit production callable injection. |
| Reproducible exact verification gate | **NOT READY** | Artifact paths, transitive hashing, and exact counters are corrected, but the 20-case denominator omits the remaining valid crash/bootstrap states and several stated loop stop contracts. See P2 finding 1. |

All six mandatory corrections implementation-ready: **NO**. Three are ready;
restart reconciliation, bootstrap/delta proof, and the resulting verification
gate remain incomplete.

### Remaining Prioritized Findings

#### P1 — `cycle_started` cannot distinguish an uncalled P136 cycle from an already committed one

The amendment records `cycle_started` before P136 and says restart must “resume
the same P136 cycle from durable P136 intent/checkpoint,” but its exact phase
fields do not bind the P136 index-read intent/receipt or an always-present P136
completion receipt (`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:365-390`).

Current P136 makes this distinction material:

- `observe_one_cycle` durably writes its index intent, optional promotion intent,
  promotion records, and checkpoint before returning the result
  (`app/services/p136_incremental_observer.py:559-620`, `:642-650`). A process
  death after checkpoint replacement but before P138 writes `p136_completed`
  therefore leaves the P138 phase at `cycle_started` although P136 committed.
- Zero-promotion cycles do not write a promotion-batch intent at all
  (`app/services/p136_incremental_observer.py:592-608`), so that artifact cannot
  serve as a general completion receipt.
- P136 intent discovery excludes receipts already consumed by the supplied
  checkpoint (`app/services/p136_incremental_observer.py:1334-1357`). Supplying
  the resulting checkpoint starts different work; supplying the starting
  checkpoint can replay against later index bytes, and checkpoint persistence is
  an unconditional atomic replacement rather than a predecessor CAS
  (`app/services/p136_incremental_observer.py:1126-1144`).

This is a normal crash window, not inconsistent evidence, so the generic
“mismatch -> fail closed” row is insufficient under the initial recovery
correction.

**Required plan correction:** add an always-durable P136 cycle completion record
that binds P136 cycle ID, receipt hash, starting/resulting checkpoint hashes, and
the exact promotion list including the empty list, or authorize an equivalent
P136 contract change. Define `cycle_started` reconciliation against that record
without invoking a new observation. Add real crash cases for both promotion and
zero-promotion cycles after P136 checkpoint commit but before the P138
`p136_completed` phase write.

#### P1 — Publisher recovery still omits fixed-bundle/state split commits

The amendment adds serialization and CASE-07 for “publisher crash after intent,”
but it does not define recovery after the fixed bundle is replaced or after
publisher state is replaced (`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:404-415`,
`:441-465`).

Current publisher ordering is:

1. read state and pending intent;
2. validate that the fixed path still matches current state;
3. write intent;
4. replace the fixed bundle;
5. replace publisher state;
6. unlink intent

(`app/services/p137_p136_handoff.py:90-120`, `:136-153`). A process death between
steps 4 and 5 leaves old state, the pending intent, and new fixed bytes. On the
next call, `_validate_publisher_state_current_bundle` runs before pending-intent
recovery (`app/services/p137_p136_handoff.py:92-101`), so the valid split commit
fails before it can complete. The current recovery test injects only immediately
after intent durability (`tests/test_p137_p136_handoff.py:225-262`). A lease
prevents concurrent writers but does not repair this single-writer crash state.

**Required plan correction:** specify the publisher's durable recovery table
inside the new lease: old state + old fixed + matching intent writes fixed then
state; old state + matching-intent fixed writes state; matching new state + fixed
unlinks the stale intent; every other byte/hash combination fails closed. Add
injections and real publisher/P138 recovery cases after fixed replacement and
after state replacement before intent cleanup.

#### P1 — A current valid bundle does not prove the proposed bootstrap promotion boundary

The amendment says a no-P138-ledger bootstrap establishes
`last_published_promotion_sequence/hash` from an already valid publisher bundle
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:392-402`). Current
validation cannot establish that claim for a non-genesis or partial bundle:

- The publisher accepts the caller-supplied `promotion_records` and creates the
  next bundle without requiring them to equal a contiguous checkpoint prefix
  (`app/services/p137_p136_handoff.py:238-301`, `:472-494`).
- The P137 adapter proves that each supplied promotion is a checkpoint member,
  but it does not prove that all earlier checkpoint promotions were supplied
  (`app/services/p137_p136_handoff.py:173-209`).
- Publisher state retains only the latest bundle sequence/hash and P136
  checkpoint hash (`app/services/p137_p136_handoff.py:37-46`), while publication
  replaces the sole fixed path (`app/services/p137_p136_handoff.py:147-152`). It
  retains no prior bundle bytes or last-published P136 promotion sequence.

Consequently, a valid current bundle containing promotion 5 does not prove that
promotions 1-4 were published, and a later fixed bundle cannot reconstruct the
overwritten history. Advancing the P138 boundary from that bundle could silently
exclude unpublished promotions.

**Required plan correction:** either restrict bootstrap to a validated genesis
bundle whose promotion sequences are exactly `1..checkpoint.next_promotion_sequence-1`,
or extend publisher state/history with a validated promotion boundary and an
explicit migration rule. Add fail-closed bootstrap cases for a partial genesis
bundle and a non-genesis current bundle without boundary evidence.

#### P2 — The exact 20-case release denominator does not cover all stated contracts

The matrix is now immutable and its evidence fields are exact, but CASE-07 covers
only the existing crash-after-intent hook and no case covers P136 commit before
the P138 phase write or bootstrap without provable contiguous history
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:436-465`). It also
does not include distinct P138 loop cases for receipt exhaustion, consecutive
failure threshold, max-cycle termination, or heartbeat/readiness cadence even
though those remain acceptance requirements earlier in the plan
(`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:111-123`, `:252-260`).

**Required plan correction:** expand or repartition the exact denominator so all
three remaining P1 states and the stated supervisor stop/readiness contracts
have exact IDs, phase paths, counters, and post-state. Keep `p138-release` totals
and the freeze manifest synchronized with the resulting denominator.

### Re-review Resolution Of Initial Findings

- Original P0 fixed-path sequence loss: **CLOSED** by reconciliation-first
  ordering and CASE-10.
- Original P1 restart reconciliation: **PARTIALLY CLOSED**; exact phase fields and
  phase rows exist, but P136 return-boundary and publisher split-commit recovery
  remain unspecified.
- Original P1 new-promotions-only contract: **PARTIALLY CLOSED**; steady-state
  delta/zero-work behavior is exact, but bootstrap proof is not.
- Original P1 lease contract: **CLOSED AT PLAN LEVEL**; publisher scope,
  serialization, lock order, contention, and release behavior are explicit.
- Original P1 exact-zero authority: **CLOSED AT PLAN LEVEL**.
- Original P1 verification reproducibility: **PARTIALLY CLOSED**; paths, hashes,
  exact maps, and real-boundary requirements are fixed, but the denominator is
  incomplete for the remaining durable states and stated loop contracts.

### Re-review Validation Evidence

Fresh current-source baseline:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/private/tmp/uv-cache \
  uv run --no-sync --extra dev pytest -q -p no:cacheprovider \
  tests/test_p136_incremental_observer.py \
  tests/test_p136_runner.py \
  tests/test_p137_p136_handoff.py \
  tests/test_p137_runtime.py \
  tests/test_p137_authority_boundary.py
```

Result: exit 0; all collected tests passed, with one existing Starlette/httpx
deprecation warning. This confirms the current component behavior cited above;
it does not validate the missing P138 recovery states.

Re-reviewed hashes:

```text
576dff2d7086418b816d8984315b3552b2d1440cccf05d65f50aaa5468788d13  .omx/plans/opscat-p138-observation-to-triage-supervisor.md
1ee59e336dec58b11351e593e1a2abee76d208722397d066fad99e297440c8de  app/services/p136_incremental_observer.py
d1074cbc8c47d25299fb3644324f82f61760ff14c422d03f066ce741225a1b29  app/services/p137_p136_handoff.py
2844b4acac1ab28f138e4398ca417a8ec1f91ed02e36e974c87b4300b0184f35  app/services/p137_runtime.py
92939cf0f34754b8ebb3d4691676c1ed57a50233b76ad5abc2f37905c2319cfb  tests/test_p137_p136_handoff.py
616c022b9cb71d9d55d29e533c35018cf513c28fef771a4fb658249f1d4f83f9  tests/test_p137_runtime.py
```

### Re-review Gate

Do not approve implementation from this amendment until the three P1 findings
are incorporated with exact owning files and real crash/bootstrap tests. The
approval rule remains P0=0 and P1=0.

---

## Final Re-review — Second Mandatory Amendment

Final re-review date: 2026-07-14
Repository commit: `1da71a08946d42ab4453918f6737a27901bab3e5`
Plan SHA-256: `37f9f91c8a7ce11ad4625a6fbe79c6069c6bc7a0f631584cfd98c1af3ff0552e`

### Definitive Verdict

**REJECT**

Finding count: P0=0, P1=1, P2=0.

The Second Mandatory Amendment closes the prior publisher split-commit,
bootstrap-history, lease, authority, artifact-flow, and matrix-count findings.
It does not close the P136 checkpoint-to-cycle-completion split commit. Approval
therefore fails because P1 is not zero.

### Required Area Assessment

| Required area | Final status | Source-bound conclusion |
| --- | --- | --- |
| Always-durable P136 completion record scope/recovery | **NOT READY — P1** | The record is specified after the checkpoint, leaving a crash window in which the checkpoint is durable but the completion record is absent. Current P136 cannot resume that consumed receipt from the resulting checkpoint. |
| All publisher split commits | **READY** | The amendment changes recovery to inspect prior state, intent, and fixed bytes before enforcing state/fixed equality, and covers intent-fsync, fixed-replacement, and state-replacement boundaries. Reconciliation-first handling covers a fully committed current bundle before a P138 phase update. |
| Genesis-only bootstrap proof | **READY** | Bootstrap is restricted to sequence 1, null predecessor, exact contiguous promotion sequences, complete checkpoint promotion-key membership, and matching P137 chain/checkpoint. Partial genesis and non-genesis state fail closed. |
| Exact 28-case denominator | **COUNT EXACT; RECOVERY COVERAGE NOT READY** | The plan contains exactly 28 unique case IDs and requires 28/28 throughout. CASE-21/22 cover checkpoint commit before the P138 phase write only when the new completion record exists; they do not specify or prove recovery from a crash before that record is durable. This is part of the single P1 below. |
| Leases | **READY** | Paths are exact/disjoint, the order is P138 -> P136 -> publisher -> P137 -> P138 final write, the publisher lease covers its entire operation, and conflicts cannot advance publisher/P138 state. |
| Exact-zero authority | **READY** | The exact 15-key P138 tuple matches current P136/P137, strict integer-zero validation is required at every layer, aggregates are rebuilt, and evaluator-only crash/signal/guard activity is separated. |
| Artifact flow | **READY** | Preliminary writes the same tracked matrix/manifest paths consumed by final mode; the freeze/review bind the transitive P136/P137/P138 scope; `p138-release` consumes frozen inputs, rejects drift, and requires 28/28. |

### Remaining P1 — The new P136 completion record has its own uncovered split commit

The amendment requires `p136.cycle_completion.v1` to be atomically written
*after* the resulting checkpoint is durable and before `observe_one_cycle`
returns (`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:494-511`).
Atomic replacement of the completion file does not make it atomic with the
earlier checkpoint replacement. A process can die after checkpoint file and
parent fsync but before the completion file exists.

That state is not recoverable through the amendment's stated fallback that
“absence permits P136's existing matching-intent recovery”:

- Current P136 advances the checkpoint before returning
  (`app/services/p136_incremental_observer.py:580-650`; checkpoint replacement at
  `app/services/p136_incremental_observer.py:1126-1144`).
- The resulting checkpoint consumes the selected receipt. Intent discovery
  explicitly excludes consumed receipts
  (`app/services/p136_incremental_observer.py:1334-1357`).
- Intent validation requires the intent's starting checkpoint hash to equal the
  checkpoint supplied for recovery
  (`app/services/p136_incremental_observer.py:1313-1331`). It therefore cannot
  validate the starting-checkpoint intent against the already advanced
  checkpoint.
- Empty-promotion cycles write no promotion intent
  (`app/services/p136_incremental_observer.py:592-608`), so the missing
  completion's exact empty promotion list cannot be recovered through that
  artifact under the current contract.

The `cycle_started` P138 phase binds only the starting checkpoint hash, not the
canonical starting checkpoint bytes. Consequently, it cannot safely re-invoke
the current P136 cycle or reconstruct and validate the missing completion from
the resulting checkpoint. Retrying with the advanced checkpoint selects new
work; retrying with unavailable/stale starting state risks replay against later
index bytes.

**Mandatory correction:** define a recoverable checkpoint/completion protocol
inside the P136 lease. For example, persist an exact cycle-completion intent
before checkpoint replacement that binds the canonical starting and resulting
checkpoint data, receipt, cycle ID, and ordered promotion list including empty;
then define exact old/new checkpoint + intent + completion recovery tuples and
cleanup. Alternatively, use one durable object/transaction that makes the
checkpoint and completion boundary indivisible. CASE-21 and CASE-22 must inject
death specifically after checkpoint parent fsync and before completion-record
fsync, for nonempty and empty cycles, and prove recovery without another index
read or receipt consumption. Absence of a completion record must not be routed
to current matching-intent discovery without an explicit compatible contract
change.

### Closed Findings From The Prior Re-review

- Publisher recovery: **CLOSED** by the exact old/intent/fixed tuple table and
  the three evaluator-only split-commit injections.
- Bootstrap promotion boundary: **CLOSED** by genesis-only contiguous/full
  checkpoint proof and fail-closed non-genesis/partial cases.
- Exact denominator: **CLOSED numerically** at 28 unique IDs; the only remaining
  coverage defect is the P136 intra-cycle boundary described above.
- Loop stop/readiness coverage: **CLOSED** by CASE-26 through CASE-28.
- Leases and exact-zero authority: **CLOSED AT PLAN LEVEL**.
- Frozen artifact flow and transitive hash binding: **CLOSED AT PLAN LEVEL**.

### Final Validation Evidence

Fresh current-source baseline:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/private/tmp/uv-cache \
  uv run --no-sync --extra dev pytest -q -p no:cacheprovider \
  tests/test_p136_incremental_observer.py \
  tests/test_p136_runner.py \
  tests/test_p137_p136_handoff.py \
  tests/test_p137_runtime.py \
  tests/test_p137_authority_boundary.py
```

Result: exit 0; all collected tests passed, with one existing Starlette/httpx
deprecation warning. These tests confirm the current P136/P137 semantics cited
above; no current test can validate the not-yet-implemented completion record.

Final reviewed hashes:

```text
37f9f91c8a7ce11ad4625a6fbe79c6069c6bc7a0f631584cfd98c1af3ff0552e  .omx/plans/opscat-p138-observation-to-triage-supervisor.md
1ee59e336dec58b11351e593e1a2abee76d208722397d066fad99e297440c8de  app/services/p136_incremental_observer.py
d1074cbc8c47d25299fb3644324f82f61760ff14c422d03f066ce741225a1b29  app/services/p137_p136_handoff.py
2844b4acac1ab28f138e4398ca417a8ec1f91ed02e36e974c87b4300b0184f35  app/services/p137_runtime.py
43ff53f592fa2e3665328b6be7fa3a787ed05ef918fb4e621abb389b7c95fdc8  app/services/p137_contracts.py
b2d4561f04f7566149b9a9a077314a6fc823283888565ff30b94e74ae7947a5f  app/services/p137_release_evidence.py
2309c86b610ee6ca9a807421d38bf5e969a8d974c76a575ac606d61c0a43863a  tests/test_p136_incremental_observer.py
92939cf0f34754b8ebb3d4691676c1ed57a50233b76ad5abc2f37905c2319cfb  tests/test_p137_p136_handoff.py
616c022b9cb71d9d55d29e533c35018cf513c28fef771a4fb658249f1d4f83f9  tests/test_p137_runtime.py
90d9014aa9222bf89630cf8453852906b4b5af7b12136beae324ef2a5c85b923  scripts/verify.sh
```

Verdict: **REJECT** — P0=0, P1=1, P2=0.
Plan hash: `37f9f91c8a7ce11ad4625a6fbe79c6069c6bc7a0f631584cfd98c1af3ff0552e`

## Third Final Re-review — Third Mandatory Amendment

Third final re-review date: 2026-07-14
Repository commit: `1da71a08946d42ab4453918f6737a27901bab3e5`
Plan SHA-256: `d9f76e9e08e6c0416f2f16ef818a5f2545688e37ce97bc7b13d5614c7e1cadbf`

### Definitive Verdict

**APPROVE**

Finding count: P0=0, P1=0, P2=0.

The Third Mandatory Amendment closes the sole remaining P1. It places a durable,
full-result P136 cycle outcome intent before checkpoint replacement, changes that
same deterministic outcome file to completion only after the bound checkpoint is
durable, and makes both sides of the checkpoint boundary recoverable without a
new index read, receipt, or cycle. The approval rule P0=0 and P1=0 is satisfied.

### Sole Remaining P1 Resolution

Current P136 writes promotion intent/records before advancing the checkpoint
(`app/services/p136_incremental_observer.py:589-620`), consumes the selected
receipt in that resulting checkpoint
(`app/services/p136_incremental_observer.py:1586-1611`), and cannot discover its
old index-read intent after that receipt is consumed
(`app/services/p136_incremental_observer.py:1313-1357`). Those current semantics
are exactly why a post-checkpoint-only completion record was insufficient.

The amended order at
`.omx/plans/opscat-p138-observation-to-triage-supervisor.md:567-581` is now exact:

1. After all promotion records are durable and before checkpoint replacement,
   atomically persist `p136.cycle_outcome_intent.v1` with the config/cycle/receipt,
   starting checkpoint hash, complete resulting checkpoint bytes/hash, and exact
   ordered promotion sequence/hash list including empty.
2. Atomically replace the checkpoint with exactly the checkpoint bound by that
   intent.
3. Atomically replace the same deterministic outcome file with
   `p136.cycle_completion.v1`, binding the committed checkpoint, then return.

This removes the prior checkpoint-without-recoverable-outcome state. A crash
before the checkpoint leaves the durable intent plus starting checkpoint; a
crash after the checkpoint leaves the same intent plus its bound resulting
checkpoint; a completed cycle leaves completion plus that resulting checkpoint.

### Recovery Tuple And P138 Same-cycle Use

The recovery table at plan lines 583-592 is complete for the valid protocol
states and fail-closed for every other tuple:

- intent + starting checkpoint validates exact promotion bytes (or exact empty),
  installs the bound resulting checkpoint, and writes completion;
- intent + bound resulting checkpoint writes completion;
- completion + bound resulting checkpoint returns/reconciles the completed cycle;
- no outcome + starting checkpoint permits the original observation path;
- every predecessor/hash/byte/receipt/promotion disagreement preserves the last
  valid checkpoint and fails closed.

Recovery occurs under the P136 lease and before another receipt is consumed.
Plan lines 594-598 also require P138 `cycle_started` reconciliation to invoke
that P136 recovery path, advance from the returned/loaded completion, and never
allocate a fresh receipt or cycle. This is the required same-cycle behavior for
both promotion and empty outcomes.

### Exact 30-case Flow

**READY.** The plan contains exactly 30 unique IDs, `P138-CASE-01` through
`P138-CASE-30`, with no duplicate ID. CASE-01 through CASE-28 retain their prior
meanings. CASE-29 and CASE-30 cover promotion and empty crashes after outcome-
intent fsync but before checkpoint replacement; CASE-21 and CASE-22 remain their
complementary crashes after checkpoint replacement but before completion
replacement. Together they prove both halves of the two-phase boundary, no
extra receipt, exactly-once publication for a nonempty outcome, and no
publication/P137 call for an empty outcome.

Plan lines 608-610 require runner, profile, totals, freeze manifest, final review,
and `p138-release` to consume the same exact 30/30 denominator and explicitly
supersede every stale earlier 20/20 or 28/28 statement. The tracked preliminary
to final to freeze/review to release artifact flow remains unchanged.

### Prior Closed Gates Remain Closed

- Original P0 fixed-path sequence loss and reconciliation-first sequencing:
  **CLOSED**; current bundle acceptance/finalization still precedes new P136 work.
- Exact contiguous new-promotion delta and zero-work suppression: **CLOSED**.
- Publisher intent/fixed/state split-commit recovery: **CLOSED**; the Third
  Amendment does not alter the prior exact tuple table or its three crash points.
- Genesis-only bootstrap and fail-closed partial/non-genesis history: **CLOSED**.
- P138/P136/publisher/P137 leases, disjoint paths, and lock order: **CLOSED AT
  PLAN LEVEL**.
- Exact 15-key zero-authority contract and evaluator/runtime separation: **CLOSED
  AT PLAN LEVEL**.
- Receipt-exhaustion, failure-threshold, finite-cycle, heartbeat/readiness,
  stale/deadman, and safe-signal coverage: **CLOSED** through CASE-26 to CASE-28.
- Frozen artifact flow, transitive source binding, and independent final review:
  **CLOSED AT PLAN LEVEL**, now with the 30/30 denominator.

No Third Amendment wording weakens or conflicts with those superseding plan
contracts. The relevant current P136, publisher, P137, release-validator, test,
and verification-script hashes are unchanged from the Second Mandatory
Amendment re-review.

### Third Final Validation Evidence

Fresh current-source baseline:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/private/tmp/uv-cache \
  uv run --no-sync --extra dev pytest -q -p no:cacheprovider \
  tests/test_p136_incremental_observer.py \
  tests/test_p136_runner.py \
  tests/test_p137_p136_handoff.py \
  tests/test_p137_runtime.py \
  tests/test_p137_authority_boundary.py
```

Result: exit 0; all collected tests passed, with one existing Starlette/httpx
deprecation warning. These tests confirm the current P136/P137 baseline semantics;
the reviewed document is a plan, so the new P136 outcome protocol remains an
implementation acceptance obligation rather than a claim that it already exists.

Structural matrix check: 30 unique case IDs, exactly `P138-CASE-01` through
`P138-CASE-30`, and no duplicates.

Final reviewed hashes:

```text
d9f76e9e08e6c0416f2f16ef818a5f2545688e37ce97bc7b13d5614c7e1cadbf  .omx/plans/opscat-p138-observation-to-triage-supervisor.md
1ee59e336dec58b11351e593e1a2abee76d208722397d066fad99e297440c8de  app/services/p136_incremental_observer.py
d1074cbc8c47d25299fb3644324f82f61760ff14c422d03f066ce741225a1b29  app/services/p137_p136_handoff.py
2844b4acac1ab28f138e4398ca417a8ec1f91ed02e36e974c87b4300b0184f35  app/services/p137_runtime.py
43ff53f592fa2e3665328b6be7fa3a787ed05ef918fb4e621abb389b7c95fdc8  app/services/p137_contracts.py
b2d4561f04f7566149b9a9a077314a6fc823283888565ff30b94e74ae7947a5f  app/services/p137_release_evidence.py
2309c86b610ee6ca9a807421d38bf5e969a8d974c76a575ac606d61c0a43863a  tests/test_p136_incremental_observer.py
92939cf0f34754b8ebb3d4691676c1ed57a50233b76ad5abc2f37905c2319cfb  tests/test_p137_p136_handoff.py
616c022b9cb71d9d55d29e533c35018cf513c28fef771a4fb658249f1d4f83f9  tests/test_p137_runtime.py
90d9014aa9222bf89630cf8453852906b4b5af7b12136beae324ef2a5c85b923  scripts/verify.sh
```

Verdict: **APPROVE** — P0=0, P1=0, P2=0.
Plan hash: `d9f76e9e08e6c0416f2f16ef818a5f2545688e37ce97bc7b13d5614c7e1cadbf`
