# P107 - Canary Prevention Executor

P107 is the local/mock and isolated test-harness executor for preventive
canary episodes. It consumes P106 gate-eligible evidence, recomputes the P107
gate from the complete canonical P106 payload, checks cohorts and policy again,
records append-only audit evidence, and either succeeds, rolls back, escalates,
or blocks.

Boundary: P107 adds no auth, no production mutation, no live remediation
runtime, no production adapters, no credential reads, no network calls, no
shell execution, and no cloud or database mutation. P106 eligibility remains
evidence only, with `p107_unlocked=false`.

## Tickets

- P107-000 - State machine contract.
- P107-001 - Audit schemas, WAL, and canonical hashing.
- P107-002 - Canonical P106 handoff recompute.
- P107-003 - Treatment/control cohort fingerprints.
- P107-004 - Immediate policy recheck.
- P107-005 - Durable idempotency, crash consistency, and concurrency.
- P107-006 - Local/mock harness only.
- P107-007 - Static authority boundary and runtime sentinels.
- P107-008 - Guardrails, outcomes, rollback, and no repeat.
- P107-009 - Executor integration.
- P107-010 - Replay gate, independent review schema, and outcome report.
- P107-011 - Fixture matrix and evidence CLI.
- P107-012 - Docs, verification, and release evidence.

## Verification

Run the canonical P107 release profile:

```bash
bash scripts/verify.sh --profile p107-release
```

The profile includes all 15 P107 release test files and the canary evidence CLI
smoke against `evals/prevention/p107_canary_cases.json`.

## Release Boundary

P107 release evidence is valid only for local/mock or isolated test-harness
behavior. It does not prove production rollout, real connector execution,
credential handling, hosted auth, live remediation, or unattended production
operation.

## P108 Handoff

P108 receives only deterministic offline replay evidence from a complete P107
audit chain. A P108 handoff requires matching audit, report, and replay hashes
plus fresh independent review JSON. Missing or stale review evidence keeps
`p108_replay_gate_ready=false`.
