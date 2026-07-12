# P127-001: chaos fault catalog and injection boundaries

## Goal

Define future fail-closed chaos faults and allowed injection scopes.

## Contract

- Catalog evidence, replay, clock, restart, validation, rollback, cleanup,
  target, and policy faults.
- Limit injection to local, sandbox, replay, or disposable-lab scope.
- Reject real staging, production, credentialed, or live customer targets.

## Acceptance

Future chaos tests can prove scope before injecting faults.

## Stop Rules

Stop if fault injection can reach real staging, production, credentials, or
live customer connectors.

