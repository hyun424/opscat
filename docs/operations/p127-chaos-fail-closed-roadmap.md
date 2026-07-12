# P127 Chaos Fail-Closed Roadmap / PRD

## Objective

P127 plans chaos testing for fail-closed behavior. It defines how future
implementation can inject controlled failures into local, sandbox, replay, and
disposable-lab flows and prove OpsCat refuses unsafe continuation.

P127 is documentation-only and implementation is pending. It creates no source
work, test work, chaos harness, infrastructure access, credential requirement,
staging access, production access, or mutation path by itself.

## Product Claim

P127 may claim a planned fail-closed chaos qualification framework after
future implementation and verification pass.

P127 may not claim production chaos testing, production resilience, real
staging chaos, credentialed execution, auth completion, operator replacement,
or production-safe autonomy.

Required limitation statement:

```text
P127 qualifies only planned fail-closed chaos behavior in local, sandbox,
recorded-replay, and disposable-lab scopes. It does not run chaos against real
staging or production. Auth is deferred, mutation authority outside disposable
lab scope is zero, and unsafe or uncertain conditions must fail closed.
```

## Source Context

- P125 supplies long-running resilience and restart planning.
- P126 supplies disposable-lab action boundaries.

P127 tests refusal, containment, rollback, and evidence preservation under
faults; it does not add new authority.

## Non-Authority Boundary

Every P127 artifact preserves these invariants:

- auth is deferred;
- credentials, secrets, real staging identity, production identity, and
  credential scopes are out of scope;
- real staging and production chaos are forbidden;
- mutation remains limited to future P126 disposable-lab fixtures;
- unsafe, ambiguous, partially observed, or authority-expanding conditions
  must fail closed;
- fail-open behavior blocks promotion.

Every future evidence bundle must report exact-zero credential, real staging,
production, live customer connector, non-lab mutation, L4+, free-form action,
LLM command, and authority escape counters.

## Chaos Surfaces

- Fault catalog for missing evidence, stale evidence, malformed telemetry,
  clock skew, replay corruption, restart interruption, validation failure,
  rollback failure, cleanup failure, target ambiguity, and policy conflict.
- Fail-closed decision record with reason, blocked action, operator-visible
  message, replay receipt, and authority counters.
- Containment checks for no action, no retry storm, no data loss, no hidden
  mutation, and no claim promotion after failure.

## Phases

- Phase 0 - Documentation, test spec, plan review, verification handoff, and
  ticket handoff.
- Phase 1 - Chaos fault catalog and injection boundaries.
- Phase 2 - Fail-closed decision records and operator-visible reasons.
- Phase 3 - Containment, rollback, cleanup, and data preservation checks.
- Phase 4 - Claim controls and exact-zero authority counters.
- Phase 5 - Verification handoff and P128 dependency gate.

## Tickets

1. `[planned] P127-001` - chaos fault catalog and injection boundaries
2. `[planned] P127-002` - fail-closed decision records and operator-visible reasons
3. `[planned] P127-003` - containment, rollback, cleanup, and data preservation
4. `[planned] P127-004` - claim controls and authority counters
5. `[planned] P127-005` - verification handoff and UX dependency gate

## Release Gates

- Downstream implementation may start only after all P127 planning artifacts
  and tickets exist and are accepted.
- Every unsafe, ambiguous, or authority-expanding condition fails closed.
- No chaos target is real staging or production.
- Evidence records the failure reason and blocked action.
- Implementation remains pending until future source and test changes are
  explicitly authorized and verified.

## Executable Contract

- Service: `app/services/p127_chaos_validation.py`
- Runner: `scripts/run_p127_chaos_validation.py`
- Tests: `tests/test_p127_chaos_validation.py`
- Verify profile: `p127-release`
- Input: `evals/p127/input/chaos-scenarios.json`
- Outputs: `evals/p127/chaos-report.json`, `evals/p127/release-evidence.json`
- Schemas: `p127.chaos_scenario.v1`, `p127.failure_receipt.v1`,
  `p127.release_evidence.v1`

The suite contains at least 40 local cases spanning corrupted evidence, stale
hashes, partial writes, restart interruption, validation ambiguity, rollback
failure, duplicate delivery, retry exhaustion, malformed configuration,
prompt injection, and authority drift. Gates are fail-open count 0, authority
escape 0, duplicate effects 0, lost records 0, retry attempts at most 3,
deterministic replay 1.0, visible fail-closed reasons 1.0, and exactly-zero
credential, staging, production, and external mutation authority.

Verification commands are the targeted pytest file, the runner, and
`bash scripts/verify.sh p127-release`.
