# P126-004: cleanup, destruction proof, and non-lab counters

## Goal

Define cleanup, destruction proof, and non-lab authority counters.

## Contract

- Require cleanup receipts and destruction receipts for every mutable lab
  resource.
- Report real staging, production, credential, live-call, and authority escape
  counters as exactly zero.
- Block promotion on any missing or nonzero counter.

## Acceptance

Future evidence proves lab resources were destroyed and no non-lab mutation
occurred.

## Stop Rules

Stop if cleanup cannot be proven, destruction is missing, or any non-lab
authority counter is nonzero.

