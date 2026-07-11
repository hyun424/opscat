# P107 Canary Prevention Executor

## Outcome

P107 consumes P106 gate-eligible evidence and runs a prevention-only canary
executor inside local/mock or isolated test-harness boundaries. It can attempt
only registered safe capabilities from the P106 preventive registry, after
recomputing the P106 gate from complete canonical evidence and after an
immediate policy recheck.

P107 is not a production executor. It grants no auth, credential, network,
shell, cloud, database, live adapter, or production mutation authority.

## Preconditions

- P106 evidence must be complete and fresh enough for
  `evaluate_p107_unlock_gate()` to pass when recomputed in-process.
- P106 must still report `p107_unlocked=false`; P107 treats
  `p107_unlocked=true` as invalid or forged evidence.
- Caller-provided `p107_gate_eligible` values, copied booleans, summarized
  evidence, or hand-authored eligibility claims are never authority.
- Treatment and control cohorts must have equivalent bounded fingerprints.
- `PreventiveSafetyGateResult` must be recomputed immediately before every
  attempt.

## Boundaries

- Local/mock or isolated test harness only.
- No auth or session scope.
- No production adapters or live connector transports.
- No credential or environment-secret reads.
- No network calls.
- No shell or subprocess execution authority.
- No Kubernetes, cloud, or database mutation.
- No production mutation, production rollout, or unattended production
  operation.
- No reuse of `ActionExecutionAttempt` or the incident approval execution path
  as the P107 audit source of truth.

## Primary Artifacts

- `app/services/prevention_state_machine.py`
- `app/services/prevention_episode_audit.py`
- `app/services/prevention_p106_handoff.py`
- `app/services/prevention_cohort_fingerprints.py`
- `app/services/prevention_policy_preflight.py`
- `app/services/prevention_durable_idempotency.py`
- `app/services/prevention_canary_harness.py`
- `app/services/prevention_authority_sentinel.py`
- `app/services/prevention_guardrail_rollback.py`
- `app/services/prevention_outcome_report.py`
- `scripts/run_prevention_canary_evidence.py`
- `evals/prevention/p107_canary_cases.json`
- `docs/tickets/p107/README.md`

## Ticket Sequence

1. P107-000 state machine contract.
2. P107-001 audit schemas, WAL, and canonical hashing.
3. P107-002 canonical P106 handoff recompute.
4. P107-003 treatment/control cohort fingerprints.
5. P107-004 immediate policy recheck.
6. P107-005 durable idempotency, crash consistency, and concurrency.
7. P107-006 local/mock harness only.
8. P107-007 static authority boundary and runtime sentinels.
9. P107-008 guardrails, outcomes, rollback, and no repeat.
10. P107-009 executor integration.
11. P107-010 replay gate, independent review schema, and outcome report.
12. P107-011 fixture matrix and evidence CLI.
13. P107-012 docs, verification, and release evidence.

## Required Release Profile

Targeted P107 release profile:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_prevention_p106_handoff.py \
  tests/test_prevention_canary_fingerprints.py \
  tests/test_prevention_policy_preflight.py \
  tests/test_prevention_state_machine.py \
  tests/test_prevention_episode_audit.py \
  tests/test_prevention_canary_harness.py \
  tests/test_prevention_canary_executor_contract.py \
  tests/test_prevention_canary_idempotency.py \
  tests/test_prevention_canary_concurrency.py \
  tests/test_prevention_canary_crash_consistency.py \
  tests/test_prevention_canary_rollback.py \
  tests/test_prevention_canary_fixture_matrix.py \
  tests/test_prevention_outcome_report.py \
  tests/test_prevention_static_authority_boundary.py \
  tests/test_p107_release_evidence.py
```

Evidence CLI smoke:

```bash
uv run --no-sync --extra dev python scripts/run_prevention_canary_evidence.py \
  --cases evals/prevention/p107_canary_cases.json \
  --output-json /tmp/opscat-p107-canary-evidence.json \
  --output-md /tmp/opscat-p107-canary-evidence.md
```

Canonical wrapper:

```bash
bash scripts/verify.sh --profile p107-release
```

The docs and full profiles also include P107 release coverage. Missing P107
fixtures, CLI, service modules, or release-evidence contracts fail closed.

## Required Evidence

P107 release evidence must report:

- duplicate, crash-resume, and concurrent duplicate attempt counts are `0`;
- stale or forged P105/P106 eligibility never executes;
- policy flips, cohort escape, telemetry loss, guardrail breach,
  non-improvement, rollback failure, and repeat-after-rollback cases fail safe;
- deterministic replay is true and tamper, reorder, sequence gaps,
  truncation, partial records, duplicate-parent forks, impossible transitions,
  and append-after-terminal cases are rejected;
- runtime and static authority boundary checks pass;
- authority counters for auth, credential reads, production adapters,
  production mutation, shell execution, network calls, cloud mutation, and
  database mutation are exactly false or zero;
- P106 evidence remains `p107_unlocked=false` and P107 recomputes eligibility
  instead of trusting caller-supplied booleans.

## P108 Handoff

P108 may consume only immutable offline replay evidence from P107. The handoff
requires a complete terminal audit chain, stable replay hash, stable report
hash, matching expected terminal head hash, exact zero authority counters, and
a fresh independent review JSON using
`schema_version=p107.independent_review.v1`.

If the matching independent review artifact is absent, stale, mismatched, or
non-passing, P107 evidence must report `independent_review_present=false` or
`p108_replay_gate_ready=false`. P107 must not self-approve P108.

## Stop Conditions

Stop and do not claim P107 complete if any forbidden authority path appears,
P106 must be relaxed, `ActionExecutionAttempt` becomes the prevention audit
source, caller-supplied eligibility is trusted, policy preflight can be skipped,
WAL intent is not durable before a local/mock effect, replay is non-deterministic,
or P108 handoff evidence is incomplete.
