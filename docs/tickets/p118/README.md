# P118 tickets

P118 defines a local/mock/sandbox reactive execution substrate for signed,
frozen P115 action packs selected by P117. It covers operation contracts, WAL,
CAS, idempotency, leases, approval, validation, rollback, crash recovery,
replay, and frozen fail-closed release gates.

P118 is documentation-only at this stage. Auth is deferred, credentials are out
of scope, production mutation is forbidden, L3 is the maximum level, and every
non-local authority counter must remain exactly zero.

1. `[planned] P118-001` - substrate operation contract
2. `[planned] P118-002` - WAL, CAS, and idempotency ledger
3. `[planned] P118-003` - lease owner and reactive worker loop
4. `[planned] P118-004` - signed action-pack verification
5. `[planned] P118-005` - approval policy and authority counters
6. `[planned] P118-006` - validation, rollback, and postcheck
7. `[planned] P118-007` - crash recovery and replay
8. `[planned] P118-008` - frozen evaluation and release gates

See `docs/operations/p118-reactive-execution-substrate-roadmap.md`,
`docs/operations/p118-test-spec.md`, and
`docs/operations/p118-plan-review.md`.

Every P118 ticket preserves local/mock/sandbox-only execution, auth deferral,
no credentials, no production mutation, no live connectors, no online policy
writes, no L4+ actions, signed action-pack verification, deterministic
fail-closed approval, rollback/validation evidence, crash recovery, and exact
authority counters.
