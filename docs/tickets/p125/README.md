# P125 tickets

P125 defines the long-running shadow resilience planning phase for OpsCat. It
covers local/sandbox/replay endurance, cost, data loss, and restart behavior.

Implementation is pending. Auth is deferred, credentials are out of scope,
production and staging mutation are forbidden, live proof claims are
forbidden, and every authority counter must remain exactly zero.

1. `[planned] P125-001` - long-run manifest and resource envelope
2. `[planned] P125-002` - restart and recovery matrix
3. `[planned] P125-003` - data-loss ledger and durability assertions
4. `[planned] P125-004` - cost reporting and degradation gates
5. `[planned] P125-005` - verification handoff and resilience dependencies

See `docs/operations/p125-long-running-shadow-resilience-roadmap.md`,
`docs/operations/p125-test-spec.md`,
`docs/operations/p125-plan-review.md`, and
`docs/operations/p125-verification-handoff.md`.

Schema marker: `p125.ticket_index.v1`.

