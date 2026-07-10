# P106 Preventive Action Planner

## Outcome

P106 turns a P105 release-qualified forecast and a P104 sufficient evidence
handoff into a ranked preventive intervention plan. It compiles advisory
capabilities through a closed registry into `ActionRequest` plus
`PolicyContext`, evaluates expected value, and records policy, simulation,
blast-radius, rollback, canary, post-check, and incident-memory evidence.

P106 does not execute the plan. It is a simulation-only P107 handoff layer.

## Prerequisites

- P104 must provide a `sufficient_for_policy_handoff` envelope with fresh,
  cited, non-conflicting critical evidence.
- P105 must be validated through `validate_p105_release_qualified_artifact()`.
  Caller-provided release booleans, copied gate rows, hashes, timestamps, or
  authority maps are not sufficient.
- P105 release evidence must prove every canonical P106 gate row:
  `held_out_calibration`, `per_family_release_metrics`,
  `global_release_metrics`, `real_derived_transfer`, and `safety_boundary`.
- The authority map must exactly match `G006_ZERO_AUTHORITY`.

## Boundaries

- No auth or session scope.
- No production mutation.
- No live remediation runtime.
- No production adapters, credential use, shell execution, or cloud/database
  mutation.
- No default external model calls.
- Optional LLM output is advisory only; it cannot set expected value, override
  policy, change forecast probability, bypass gates, or unlock P107.
- All P106 results keep `execution_enabled=false`, `simulation_only=true`, and
  `p107_required_for_execution=true`, including read-only actions and
  `PolicyDecision.ALLOW`.

## Primary Artifacts

- `app/services/p105_release_prerequisite.py`
- `app/services/preventive_capability_registry.py`
- `app/services/preventive_action_planner.py`
- `app/services/preventive_expected_value.py`
- `app/services/preventive_safety_gate.py`
- `app/services/prevention_planning_lab.py`
- `app/services/preventive_action_llm_adapter.py`
- `app/services/preventive_action_benchmark.py`
- `scripts/run_preventive_action_benchmark.py`
- `evals/prevention/p106_capability_registry.json`
- `evals/prevention/p106_planner_cases.json`
- `evals/prevention/p106_treatment_control_cases.json`
- `evals/prevention/p106_benchmark_cases.json`
- `tests/fixtures/p106_shared_fail_closed_cases.json`
- `docs/tickets/p106/README.md`

## Ticket Sequence

1. P106-000 release prerequisite and action-registry crosswalk.
2. P106-001 typed intervention contract and closed capability registry.
3. P106-002 P104/P105 eligibility adapter and fallback semantics.
4. P106-003 expected-value scoring and observe/escalate baselines.
5. P106-004 shared `PreventiveSafetyGateResult`.
6. P106-005 shared policy, simulator, blast-radius, and incident-memory graph.
7. P106-006 canary, rollback, and post-check contract.
8. P106-007 pre-incident treatment/control lab.
9. P106-008 optional LLM advisory proposal.
10. P106-009 adversarial benchmark and harm taxonomy.
11. P106-010 approval profile integration without auth.
12. P106-011 release documentation and verification integration.
13. P106-012 independent safety review and P107 gate lock.

## Benchmark Metrics

P106 benchmark evidence reports:

- `planner_regret`
- `harmful_action_rate`
- `unnecessary_intervention_rate`
- `safe_fallback_rate`
- `policy_fail_closed_rate`
- `mutation_shaped_simulation_only_count`
- per-arm initial-condition fingerprints
- shared fail-closed fixture results
- zero authority counters

Harm taxonomy: unregistered, shell, secret, destructive, irreversible,
production-global, unknown-blast-radius, failed-simulation,
prior-failed-memory-repeat, low-confidence, conflicting-evidence, negative EV,
and cohort interference.

## P107 Gate

P107 remains blocked unless all three operands are true in one fresh release
evidence set:

1. Every shared fail-closed fixture case passes through
   `PreventiveSafetyGateResult`.
2. `harmful_action_rate == 0.0` and every harmful taxonomy count is `0`.
3. Every mutation-shaped plan has `execution_enabled=false`,
   `simulation_only=true`, and `p107_required_for_execution=true`, with no
   forbidden execution API references.

Freshness, exact zero authority, and arm-fingerprint comparability are
fail-closed auxiliary checks. Missing evidence is false.

## Verification

Targeted implementation and release tests:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_prerequisite.py \
  tests/test_preventive_capability_registry.py \
  tests/test_preventive_expected_value.py \
  tests/test_preventive_safety_gate.py \
  tests/test_p106_execution_boundary.py \
  tests/test_preventive_action_planner.py \
  tests/test_prevention_planning_lab.py \
  tests/test_preventive_action_benchmark.py \
  tests/test_preventive_action_llm_adapter.py \
  tests/test_p106_p107_unlock.py \
  tests/test_p106_release_evidence.py \
  tests/test_p106_p105_release_archive.py
```

The prior verifier findings covered registry-hash independence, canonical P105
validation, shared registry/gate composition, planner-arm execution, bounded
metrics, shared-fixture hash validation, and fail-closed freshness/comparability.
Those findings are fixed and covered by this suite. Final independent review
completed with code review `APPROVE`, architecture/safety `CLEAR`, and verifier
`PASS`.

Offline benchmark smoke:

```bash
tmpdir="$(mktemp -d)"
cleanup() { rm -rf -- "$tmpdir"; }
trap cleanup EXIT INT TERM
p105_artifact="$(uv run --no-sync --extra dev python \
  scripts/extract_p105_release_fixture.py \
  evals/prevention/p105_release_qualified_real_derived.tar.gz \
  6aaf35285f03cc7fe68b036a8172dba1615d1e5131939b2d8ef26787dd5c7342 \
  "$tmpdir/p105")"
uv run --no-sync --extra dev python scripts/run_preventive_action_benchmark.py \
  --cases evals/prevention/p106_benchmark_cases.json \
  --p105-artifact "$p105_artifact" \
  --output-json "$tmpdir/opscat-p106-preventive-action-benchmark.json" \
  --output-md "$tmpdir/opscat-p106-preventive-action-benchmark.md"
```

Fresh SHA-pinned evidence is scored with one eligible planner evaluation,
`planner_regret=0.0`, `harmful_action_rate=0.0`,
`safe_fallback_rate=1.0`, `policy_fail_closed_rate=1.0`, one mutation-shaped
simulation-only plan, and exact zero authority. The evidence is eligible for
the P107 conjunctive gate, but P106 itself keeps `p107_unlocked=false` and
grants no execution authority.

Release profiles:

```bash
bash scripts/verify.sh --profile docs
bash scripts/verify.sh --profile eval
```

## Stop Conditions

Stop before P107 if any harm counter is nonzero, P105 prerequisite validation is
not canonical, P104 evidence is insufficient, registry/policy graph parity
diverges, a forbidden execution API reference appears, benchmark arms are not
comparable, or any P106 result can omit or flip the immutable simulation-only
boundary fields.
