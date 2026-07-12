# P126-005: verification handoff and controlled-action dependencies

## Goal

Define the P126 verification handoff and dependency gates.

## Contract

- Maintain the P126 roadmap, test spec, plan review, verification handoff,
  ticket README, and tickets P126-001 through P126-005.
- Require handoff evidence for lab isolation, preflight, simulation,
  execution, validation, rollback, cleanup, destruction, and counters.
- Mark implementation pending until future source and test evidence exists.

## Acceptance

Future P127 chaos planning can depend on lab-only action evidence without
mistaking it for real staging or production authority.

## Stop Rules

Stop if handoff omits destruction proof, non-lab counters, rejected target
evidence, or disposable-lab limitation language.

