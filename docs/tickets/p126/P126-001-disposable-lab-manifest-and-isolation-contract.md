# P126-001: disposable lab manifest and isolation contract

## Goal

Define the future manifest for disposable remediation lab targets.

## Contract

- Require labels, owner, TTL, isolation boundary, allowed target patterns,
  resource inventory, and cleanup plan.
- Reject real staging, production, shared, persistent, or unlabeled targets.
- Require non-overlap proof against protected names.

## Acceptance

Future remediation cannot start unless the mutable target is proven disposable
and lab-scoped.

## Stop Rules

Stop if lab identity is ambiguous, persistent, shared, or overlapping with
real staging or production.

