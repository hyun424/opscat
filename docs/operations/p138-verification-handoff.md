# P138 Verification Handoff

## Current status

**QUALIFIED — frozen local release evidence reproduces 30/30 cases.**

The approved P138 plan is now backed by the complete tracked qualification set:

- `evals/p138/input/observation-triage-supervisor-profile.json`;
- `scripts/run_p138_observation_triage_supervisor.py`;
- `evals/p138/output/canonical-matrix.json`;
- `evals/p138/output/freeze-manifest.json`;
- `evals/p138/output/release-evidence.json`;
- `evals/p138/final-implementation-review.json`;
- `p138-release` verification-profile wiring.

Final mode reproduced exactly 30 expected, 30 passed, and 0 failed. The tracked
release evidence hash is
`sha256:1c3cbb6fe575b17e4fcf2159ac2cff15fc90b6cd1c452acb1cb81eaa0f5c76d7`;
the final review records P0/P1/P2/P3 all at zero. The P138 evidence also binds
the exact qualified P136 and P137 evidence/review hashes. The claimed status is
`p138_local_observation_to_triage_supervisor_qualified`.

The external reviewer resume was blocked by the desktop security reviewer to
avoid transmitting uncommitted workspace code. The final artifact records that
limitation and uses the repository-local deterministic review gate; it does not
claim authenticated reviewer identity.

## Qualification claim to prove

P138 must be a reconciliation-first, production-shaped, local-only, finite
supervisor over the existing P136 observer, P136-owned fixed-path publisher,
and P137 bounded triage runtime. It must not become an observation provider,
triage engine, notifier, action system, remediation system, unattended
production daemon, or operator replacement.

A qualifying run must prove all of the following together:

- exactly 30 expected cases, 30 passed, and 0 failed;
- reconciliation before any new P136 observation or publication;
- the exact normal phase path
  `cycle_started -> p136_completed -> handoff_selected -> handoff_published -> p137_accepted -> cycle_finalized`;
- the exact zero-delta path
  `cycle_started -> p136_completed -> cycle_finalized`, with no publisher or
  P137 call;
- P136's recoverable two-phase sequence
  `p136.cycle_outcome_intent.v1` -> checkpoint replacement ->
  `p136.cycle_completion.v1` for nonempty and empty outcomes;
- a nonblocking whole-operation publisher lease and exact recovery across
  intent, fixed-path, and state split commits;
- genesis-only bootstrap with sequence 1, null predecessor, and complete
  contiguous P136 promotion history from sequence 1 through the checkpoint
  boundary;
- exact set equality with the shared 15-key zero forbidden-authority tuple;
- frozen preliminary inputs, a separate independent final implementation
  review with no unresolved P0/P1/P2 findings, final-mode no-regeneration, and
  no reviewed hash drift.

## Exact immutable case denominator

| ID | Scenario | Required terminal/post-state |
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

CASE-21 and CASE-22 prove recovery after checkpoint replacement but before the
outcome file becomes completion. CASE-29 and CASE-30 prove the complementary
recovery before checkpoint replacement. Together they must prove no additional
index read, receipt, or cycle; exactly-once publication for nonempty outcomes;
and no publisher/P137 call for empty outcomes.

## Exact authority boundary

Every config, component result, P138 phase, termination record, case
actual/expected map, rebuilt aggregate, and final release record must contain
exactly these keys with values whose type is integer and whose value is zero:

- `provider_call_count`;
- `live_connector_call_count`;
- `network_call_count`;
- `dns_lookup_count`;
- `socket_call_count`;
- `credential_read_count`;
- `environment_read_count`;
- `subprocess_launch_count`;
- `shell_execution_count`;
- `signal_count`;
- `delivery_count`;
- `remediation_count`;
- `staging_mutation_count`;
- `production_mutation_count`;
- `operator_replacement_count`.

Missing or extra keys, aliases, booleans, negative values, and nonzero values
fail closed. Evaluator process, crash, signal, and fake-guard activity remains
separate and grants no runtime authority. P138 has no authentication,
credentials, environment discovery, provider/live-connector API, network,
notification, action, remediation, staging/production mutation, or
operator-replacement capability.

## Frozen preliminary and final flow

Preliminary mode must write the reviewed inputs at the same tracked paths that
final mode consumes:

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev python scripts/run_p138_observation_triage_supervisor.py --mode preliminary --output-dir evals/p138/output
```

After preliminary mode, freeze the complete transitive P136 two-phase
cycle-outcome, publisher, P137, and P138 runtime/contracts/release validators,
runner, profile, fixtures, cases, matrix, tests, and documentation scope. A
reviewer independent from implementation must write
`evals/p138/final-implementation-review.json`, bind that frozen scope, and
record zero unresolved P0/P1/P2 findings.

Only then may final mode consume the reviewed inputs without regenerating or
overwriting them:

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev python scripts/run_p138_observation_triage_supervisor.py --mode final --canonical-matrix evals/p138/output/canonical-matrix.json --freeze-manifest evals/p138/output/freeze-manifest.json --final-implementation-review evals/p138/final-implementation-review.json --output-dir evals/p138/output
```

The historical approved plan review is not a substitute for this final
implementation review.

## Required verification sequence

Run targeted checks with the repository's fixed local cache convention:

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev pytest -q tests/test_p136_incremental_observer.py tests/test_p137_p136_handoff.py tests/test_p137_runtime.py tests/test_p138_observation_triage_supervisor.py
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev ruff check app/services/p136_incremental_observer.py app/services/p137_p136_handoff.py app/services/p138_observation_triage_supervisor.py scripts/run_p138_observation_triage_supervisor.py tests/test_p136_incremental_observer.py tests/test_p137_p136_handoff.py tests/test_p138_observation_triage_supervisor.py tests/fixtures/p136/builders.py tests/fixtures/p138/builders.py
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev mypy app/services/p136_incremental_observer.py app/services/p137_p136_handoff.py app/services/p138_observation_triage_supervisor.py scripts/run_p138_observation_triage_supervisor.py tests/test_p138_observation_triage_supervisor.py
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p138-release
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p136-release
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p137-release
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile full
git diff --check
```

`p138-release` must consume the frozen tracked files, not rebuild them. P136 and
P137 profiles remain separate; P138 may bind their qualified statuses and
hashes but may not re-claim their denominators.

## Release and withdrawal decision

Set the release status to
`p138_local_observation_to_triage_supervisor_qualified` only after all tracked
inputs exist, the independent final implementation review passes, final mode
reproduces exact 30/30 evidence without reviewed-input regeneration, every
authority value remains zero, and the complete verification sequence passes.

Keep qualification pending, or withdraw an existing claim, on any missing
artifact, hash drift, unresolved P0/P1/P2 finding, total other than 30/30,
counter-schema mismatch, nonzero forbidden authority, resource-limit failure,
or unreproducible command. Even after qualification, the claim remains
local-only and production-shaped; it is not unattended production operation.
