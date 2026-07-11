# P119-007: causal outcome attribution, recurrence, and learning

## Goal

Attribute incident outcomes using measured controls, detect recurrence, write
local/offline learning records, and enforce no online policy mutation.

## Contract

- Compare action windows against baseline, fault, validation, no-action,
  natural-recovery, wrong-action when available, and rollback windows.
- Emit one attribution label from `action_helped`, `no_action_recovered`,
  `natural_recovery`, `rollback_recovered`, `action_harmed`, `no_effect`,
  `ambiguous`, and `invalid`.
- Credit `action_helped` only when improvement beats no-action and
  natural-recovery controls inside the attribution window with no guardrail
  breach.
- Treat rollback recovery as safety recovery, not action success.
- Detect recurrence after claimed recovery and downgrade, reopen, or escalate
  learning status.
- Write local/offline learning records with hashes, denominators, split,
  fixture version, seed, and replay refs.

## Acceptance

Natural recovery and no-action recovery are never credited as action success,
missing or contaminated controls produce ambiguous or invalid attribution,
recurrence blocks false recovery claims, learning records are replayable and
non-mutating, and online policy write counters remain exactly zero.

## Stop Rules

Stop if learning can mutate online policy, tune frozen evaluation after first
score, write production thresholds, credit natural recovery as action success,
hide recurrence, omit denominators or hashes, or claim generalization beyond
local/mock/sandbox evidence.
