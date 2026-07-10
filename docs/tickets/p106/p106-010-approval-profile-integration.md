# P106-010 - Approval Profile Integration Without Auth

## Goal

Map local approval metadata into policy context and audit output without
creating auth/session scope.

## Contract

- Approval metadata can affect reporting and `requires_approval` context.
- Approval metadata cannot authorize production, prohibited, unknown, or
  executable action paths.
- Approval metadata cannot change immutable P106 boundary fields.

## Acceptance

`approved=true`, approval IDs, elevated local capabilities, and
`PolicyDecision.ALLOW` still leave every P106 result as
`execution_enabled=false`, `simulation_only=true`, and
`p107_required_for_execution=true`.
