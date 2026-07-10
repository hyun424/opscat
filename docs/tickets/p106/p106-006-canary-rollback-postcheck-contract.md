# P106-006 - Canary, Rollback, and Post-Check Contract

## Goal

Make mutation-shaped P106 plans structurally ready for P107 without making them
executable in P106.

## Contract

Every mutation-shaped candidate requires treatment cohort selector, control
selector, duration, primary metric, guardrail metrics, rollback trigger,
post-checks, and P107 handoff fields.

## Acceptance

Missing canary, rollback, guardrails, post-checks, or control cohort rejects
the candidate. Production/global canary scope is rejected. Serialization,
advisory LLM merging, approval metadata, and `PolicyDecision.ALLOW` cannot omit
or flip `execution_enabled=false`, `simulation_only=true`, or
`p107_required_for_execution=true`.
