# P125 Long-Running Shadow Resilience Roadmap / PRD

## Objective

P125 defines and now implements long-running shadow resilience evaluation for
OpsCat. The promoted deterministic local run processes 10,000 events, exercises
12 modeled interruption points, accounts for seven durable record families,
and publishes hash-bound resource, loss, duplicate, and authority evidence.

This document preserves the original plan and conservative claim boundary.
Implementation is present in `app/services/p125_shadow_resilience.py`,
`scripts/run_p125_shadow_resilience.py`, and
`tests/test_p125_shadow_resilience.py`; evidence is under `evals/p125/`.

## Product Claim

P125 may claim a verified deterministic local resilience and cost-measurement
framework for the promoted local/sandbox/shadow replay profile.

P125 may not claim production SLO compliance, live operations durability,
credentialed execution, production or staging mutation, auth completion, or
autonomous remediation safety.

Required limitation statement:

```text
P125 qualifies only planned long-running read-only shadow resilience in local,
sandbox, and recorded-replay environments. Cost, restart, and data-loss
results are not production SLO proof. Auth is deferred and all production,
staging, credential, live-call, and mutation authority counters remain zero.
```

## Source Context

- P123 supplies artifact-backed recorded replay.
- P124 supplies measured judgment-quality reporting that P125 must not degrade
  under long-running execution.

P125 measures endurance and durability; it does not add live access or action
authority.

## Non-Authority Boundary

Every P125 artifact preserves these invariants:

- auth is deferred;
- credentials, secrets, live connectors, production identity, and credential
  scopes are out of scope;
- production and staging mutation are forbidden;
- restart and recovery tests use local/sandbox/replay state only;
- cost measurement is local resource accounting, not cloud billing authority;
- data-loss claims require denominators and artifact manifests.

Every future evidence bundle must report exact-zero credential, live-call,
staging, production, mutation, shell/subprocess action, L4+, free-form action,
LLM command, and authority escape counters.

## Resilience Surfaces

- Long-run manifest with duration, event volume, replay source, hardware
  context, storage budget, and resource limits.
- Restart matrix covering clean stop, crash, power-loss simulation, partial
  write, report-write interruption, and replay resume.
- Data-loss ledger covering events, observations, judgments, receipts, audit
  records, counters, and reports.
- Cost envelope covering CPU, memory, storage, local runtime, and per-event
  resource use.

## Phases

- Phase 0 - Documentation, test spec, plan review, verification handoff, and
  ticket handoff.
- Phase 1 - Long-run manifest and resource envelope.
- Phase 2 - Restart and recovery matrix.
- Phase 3 - Data-loss ledger and durability assertions.
- Phase 4 - Cost reporting and degradation gates.
- Phase 5 - Verification handoff and P126 dependency gate.

## Tickets

1. `[implemented] P125-001` - long-run manifest and resource envelope
2. `[implemented] P125-002` - restart and recovery matrix
3. `[implemented] P125-003` - data-loss ledger and durability assertions
4. `[implemented] P125-004` - cost reporting and degradation gates
5. `[implemented] P125-005` - verification handoff and resilience dependencies

## Release Gates

- Downstream implementation may start only after all P125 planning artifacts
  and tickets exist and are accepted.
- Long-running claims include duration, event volume, resource context, and
  denominators.
- Restart evidence reports lost-record counts for every durable record type.
- Cost claims remain local/sandbox qualified.
- Promotion remains limited to the committed deterministic local profile and
  does not generalize to the real P131 process or production SLOs.

## Executable Resilience Contract

P125 implementation targets are fixed as follows:

- service: `app/services/p125_shadow_resilience.py`;
- runner: `scripts/run_p125_shadow_resilience.py`;
- tests: `tests/test_p125_shadow_resilience.py`;
- verification registry: `scripts/verify.sh`, whose `p125-release` profile must
  run the named test, regenerate the report, ledger, and release evidence, and
  validate restart coverage, loss/duplicate counts, resource gates, hashes,
  and exact-zero authority counters;
- profile: `evals/p125/input/soak-profile.json`;
- promoted outputs: `evals/p125/resilience-report.json`,
  `evals/p125/resilience-ledger.jsonl`, and
  `evals/p125/release-evidence.json`;
- schemas: `p125.soak_profile.v1`, `p125.resilience_report.v1`, and
  `p125.release_evidence.v1`.

The promoted bounded profile processes at least 10,000 replay events and
exercises 12 declared interruption points: clean stop, process crash, partial
event write, partial observation write, partial judgment write, partial receipt
write, partial audit write, partial report write, stale checkpoint, duplicated
resume request, corrupted checkpoint, and exhausted retry budget. Every durable
record family reports expected, committed, recovered, lost, and duplicated
counts.

Promotion requires lost and duplicated durable records `0`, deterministic
resume rate `1.0`, retry count no greater than `3` per interruption, maximum
pending queue depth no greater than `1,000`, p95 event latency no greater than
`250 ms`, p99 no greater than `1,000 ms`, peak traced memory no greater than
`256 MiB`, promoted artifact storage no greater than `50 MiB`, P124 quality
gate preservation, and every authority counter zero. The report records actual
duration, CPU time, platform, Python version, event volume, and all
denominators; these local measurements are not production SLO evidence.

Verification commands:

```bash
uv run --no-sync --extra dev pytest -q tests/test_p125_shadow_resilience.py
uv run --no-sync --extra dev python scripts/run_p125_shadow_resilience.py \
  --profile evals/p125/input/soak-profile.json \
  --output evals/p125/resilience-report.json \
  --ledger evals/p125/resilience-ledger.jsonl \
  --release-evidence evals/p125/release-evidence.json
bash scripts/verify.sh --profile p125-release
```
