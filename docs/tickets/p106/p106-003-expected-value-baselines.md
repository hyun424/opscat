# P106-003 - Expected-Value Scoring and Baselines

## Goal

Rank preventive candidates against observe/no-op and escalation baselines using
deterministic expected value.

## Formula

```text
probability * avoided_impact
  - intervention_harm
  - operational_cost
  - uncertainty_penalty
  - false_alert_penalty
```

## Contract

- Thresholds and penalties are explicit and reported in candidate traces.
- Raw LLM confidence is not an input.
- Negative expected value, high false-alert burden, low probability, high
  uncertainty, high harm, unsafe blast radius, and irreversible actions lose to
  observe/escalate.
- Ties choose lower blast radius, then reversible action, then stable candidate
  ID.

## Acceptance

Planner output reports components, selected baseline, regret inputs, and
deterministic tie-break trace for every ranked candidate.
