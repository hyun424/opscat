# P117-001: evidence-bound decision episode contract

## Goal

Define the immutable P117 input/output schemas that bind each decision episode
to sealed P114 lattices, signed P115 action packs, measured P116 outcomes,
utility/calibration profiles, split membership, and authority receipts.

## Contract

- Define `p117.decision_episode.v1` with P114 lattice reference, selected
  hypothesis or abstention, visible evidence IDs, missing evidence markers,
  P115 case/action-pack references, P116 outcome references, calibration
  profile, utility profile, split, seed, and authority receipt.
- Define `p117.decision_output.v1` with selected label, optional action-pack
  ID, ranked action IDs, requested evidence classes, citations, contradiction
  IDs, expected utility, utility interval, calibrated confidence, abstention
  reason, fallback reason, and LLM proposal receipt.
- Reject hidden truth, unsealed labels, invented IDs, commands, credentials,
  target selectors, mutation language, or executable fields.
- Preserve deterministic serialization and hash stability.

## Acceptance

Contract validity is 1.0 on frozen fixtures, unknown ID acceptance is 0,
authority counters are exactly zero, and repeated serialization produces stable
hashes.

## Stop Rules

Stop if the schema permits free-form actions, live connector calls, credentials,
commands, hidden labels, or any execution authority.
