# P117 tickets

P117 defines an evidence-bound action-selection agent for frozen benchmark
episodes. It consumes P114 lattices, P115 signed action packs, and P116 measured
outcomes. It can rank frozen action IDs, request typed evidence, or abstain, but
it does not execute remediation or grant authority.

1. `[planned] P117-001` - evidence-bound decision episode contract
2. `[planned] P117-002` - active evidence-acquisition taxonomy and VOI gate
3. `[planned] P117-003` - contradiction ledger and fallback semantics
4. `[planned] P117-004` - utility, calibration, and abstention policy
5. `[planned] P117-005` - deterministic selector baseline
6. `[planned] P117-006` - constrained NVIDIA proposal benchmark
7. `[planned] P117-007` - tournament scorer and frozen unseen evaluation
8. `[planned] P117-008` - release evidence, independent review, and stop gate

See `docs/operations/p117-evidence-bound-action-selection-roadmap.md`,
`docs/operations/p117-test-spec.md`, and
`docs/operations/p117-plan-review.md`.

Every P117 ticket preserves proposal-only LLM behavior, deterministic fallback,
frozen-ID selection, active evidence acquisition as metadata only, and exact-zero
production authority.
