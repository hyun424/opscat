# P106-001 - Typed Intervention Contract and Closed Capability Registry

## Goal

Define the closed registry that compiles advisory preventive capabilities into
`ActionRequest` and `PolicyContext` using one shared policy graph.

## Contract

- Capability metadata includes family, action type, environment allowlist,
  required evidence, preconditions, post-checks, canary scope, rollback trigger,
  reversibility, cost, and mutation-shaped status.
- Every capability maps to an existing `DEFAULT_ACTION_REGISTRY` entry or a
  complete validated `ActionMetadata` record loaded before `RiskEngine`
  construction.
- Production, shell, secret, database, cloud, destructive, and unknown actions
  are impossible to register.
- Registry, compiler, `RiskEngine`, `PolicyEngine`,
  `BlastRadiusService`, and `ActionSimulator` expose one canonical hash and
  share the same `RiskEngine` instance.

## Acceptance

Duplicate IDs, unresolved action types, invalid metadata, production-only
environments, missing evidence, missing rollback/post-checks for
mutation-shaped entries, and hash/object graph divergence fail closed before
planning.
