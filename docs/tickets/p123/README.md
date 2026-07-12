# P123 tickets

P123 defines the real read-only shadow telemetry attachment planning phase for
OpsCat. It covers artifact-backed real telemetry intake and recorded replay
only.

Implementation is pending. Auth is deferred, credentials are out of scope,
live proof claims are forbidden, production and staging mutation are forbidden,
and every credential, live-call, and mutation authority counter must remain
exactly zero.

1. `[planned] P123-001` - read-only telemetry artifact intake contract
2. `[planned] P123-002` - recorded replay adapter and deterministic playback
3. `[planned] P123-003` - shadow judgment outputs and evidence receipts
4. `[planned] P123-004` - no-credential guardrails and authority counters
5. `[planned] P123-005` - claim ledger, verification handoff, and dependencies

See `docs/operations/p123-real-read-only-shadow-telemetry-attachment-roadmap.md`,
`docs/operations/p123-test-spec.md`,
`docs/operations/p123-plan-review.md`, and
`docs/operations/p123-verification-handoff.md`.

Schema marker: `p123.ticket_index.v1`.

