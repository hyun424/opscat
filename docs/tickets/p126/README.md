# P126 tickets

P126 defines the controlled disposable staging-lab remediation planning phase
for OpsCat. It covers lab-only action against disposable resources and never
real staging or production.

Implementation is pending. Auth is deferred, credentials are out of scope,
real staging and production mutation are forbidden, and every non-lab
authority counter must remain exactly zero.

1. `[planned] P126-001` - disposable lab manifest and isolation contract
2. `[planned] P126-002` - lab-only remediation catalog and preflight gate
3. `[planned] P126-003` - simulation, execution receipts, validation, and rollback
4. `[planned] P126-004` - cleanup, destruction proof, and non-lab counters
5. `[planned] P126-005` - verification handoff and controlled-action dependencies

See `docs/operations/p126-controlled-disposable-staging-lab-remediation-roadmap.md`,
`docs/operations/p126-test-spec.md`,
`docs/operations/p126-plan-review.md`, and
`docs/operations/p126-verification-handoff.md`.

Schema marker: `p126.ticket_index.v1`.

