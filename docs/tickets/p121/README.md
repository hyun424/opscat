# P121 tickets

P121 defines a local/mock/sandbox proactive prevention phase for OpsCat. It
turns leading indicators into calibrated, evidence-bound, counterfactual
prevention decisions before an incident crosses the declared impact threshold.

P121 is documentation-only at this stage. Auth is deferred, credentials are out
of scope, production and staging mutation are forbidden, live connector
authority is forbidden, forecast confidence alone is not action authority, and
every production/nonlocal authority counter must remain exactly zero.

1. `[planned] P121-001` - leading indicator and forecast horizon contracts
2. `[planned] P121-002` - evidence acquisition before intervention
3. `[planned] P121-003` - counterfactual prevention utility and baselines
4. `[planned] P121-004` - false-positive and alert-fatigue controls
5. `[planned] P121-005` - deterministic approval and L0-L3 local/sandbox intervention
6. `[planned] P121-006` - validation, rollback, causal attribution, and recurrence reduction
7. `[planned] P121-007` - frozen unseen temporal/system evaluation
8. `[planned] P121-008` - docs, test spec, release evidence, crash/replay, and independent review

See `docs/operations/p121-proactive-prevention-roadmap.md`,
`docs/operations/p121-test-spec.md`, and
`docs/operations/p121-plan-review.md`.

Every P121 ticket preserves leading indicators, forecast/counterfactual
prevention, false-positive and alert-fatigue controls, evidence-before-action,
local/mock/sandbox L0-L3 only, auth deferred, exact-zero authority,
temporal/system holdouts, calibration, abstention, causal attribution, frozen
evaluation, independent review, honest claims, no production readiness
overclaim, no live connector calls, no connector writes, no production or
staging mutation, no online policy writes, no shell/subprocess/Kubernetes/
cloud/database/network mutation, no L4+ actions, no free-form action
execution, and no LLM command execution.
