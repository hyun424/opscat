# P125 tickets

P125 defines and implements deterministic long-running shadow resilience for
OpsCat. The promoted local profile covers 10,000 replay events, resource cost,
data loss, duplicate accounting, and 12 modeled interruption points.

Implementation and `p125-release` evidence exist. Auth is deferred, credentials
are out of scope, production and staging mutation are forbidden, real-process
and production durability claims are forbidden, and every authority counter
must remain exactly zero.

1. `[implemented] P125-001` - long-run manifest and resource envelope
2. `[implemented] P125-002` - restart and recovery matrix
3. `[implemented] P125-003` - data-loss ledger and durability assertions
4. `[implemented] P125-004` - cost reporting and degradation gates
5. `[implemented] P125-005` - verification handoff and resilience dependencies

See `docs/operations/p125-long-running-shadow-resilience-roadmap.md`,
`docs/operations/p125-test-spec.md`,
`docs/operations/p125-plan-review.md`, and
`docs/operations/p125-verification-handoff.md`.

Schema marker: `p125.ticket_index.v1`.
