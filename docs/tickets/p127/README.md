# P127 tickets

P127 defines the chaos fail-closed planning phase for OpsCat. It covers
controlled faults in local, sandbox, recorded-replay, and disposable-lab
scopes.

Implementation is pending. Auth is deferred, credentials are out of scope,
real staging and production chaos are forbidden, and unsafe or ambiguous
conditions must fail closed with exact-zero non-lab authority counters.

1. `[planned] P127-001` - chaos fault catalog and injection boundaries
2. `[planned] P127-002` - fail-closed decision records and operator-visible reasons
3. `[planned] P127-003` - containment, rollback, cleanup, and data preservation
4. `[planned] P127-004` - claim controls and authority counters
5. `[planned] P127-005` - verification handoff and UX dependency gate

See `docs/operations/p127-chaos-fail-closed-roadmap.md`,
`docs/operations/p127-test-spec.md`,
`docs/operations/p127-plan-review.md`, and
`docs/operations/p127-verification-handoff.md`.

Schema marker: `p127.ticket_index.v1`.

