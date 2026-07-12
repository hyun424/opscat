# P126-002: lab-only remediation catalog and preflight gate

## Goal

Define the finite remediation catalog and preflight gate for disposable lab
actions.

## Contract

- Catalog only lab-scoped actions with typed inputs, blast-radius limits,
  validation probes, rollback probes, and deny conditions.
- Preflight revalidates target identity immediately before action.
- Reject free-form action execution and L4+ authority.

## Acceptance

Future actions are blocked unless they match catalog entries and pass lab-only
preflight.

## Stop Rules

Stop if actions can target real staging, production, shared resources, or
untyped free-form commands.

