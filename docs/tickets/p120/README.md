# P120 tickets

P120 defines a non-mutating cross-system benchmark generalization phase for the
P117-P119 stack. It measures whether evidence-bound diagnosis, action
selection, local/mock/sandbox execution, validation/rollback, calibration,
abstention, and fail-closed behavior remain useful across heterogeneous,
previously unseen systems.

P120 is documentation-only at this stage. Auth is deferred, credentials are out
of scope, production and staging mutation are forbidden, live connector
authority is forbidden, read-only connector/importer conformance is not
production permission, and every authority counter must remain exactly zero.

1. `[planned] P120-001` - dataset source governance and import registry
2. `[planned] P120-002` - system-level split and near-duplicate prevention
3. `[planned] P120-003` - telemetry normalization and read-only connector contracts
4. `[planned] P120-004` - ontology mapping and identity normalization
5. `[planned] P120-005` - domain shift and OOD detection
6. `[planned] P120-006` - calibration, abstention, and baseline comparison
7. `[planned] P120-007` - frozen first-score evaluation and per-system metrics
8. `[planned] P120-008` - failure analysis, release evidence, docs, test spec, and review

See `docs/operations/p120-cross-system-generalization-roadmap.md`,
`docs/operations/p120-test-spec.md`, and
`docs/operations/p120-plan-review.md`.

Every P120 ticket preserves exact-zero authority, auth deferral, no
credentials, no production or staging mutation, no live connector calls, no
connector writes, no online policy writes, no shell/subprocess/Kubernetes/
cloud/database/network mutation, no L4+ actions, no free-form action
execution, no LLM command execution, read-only connectors only, frozen
system-level holdouts, OOD/calibration/abstention gates, per-system metrics,
independent verification, honest claim boundaries, and no production safety
overclaim.
