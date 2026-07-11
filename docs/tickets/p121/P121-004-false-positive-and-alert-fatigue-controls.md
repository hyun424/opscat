# P121-004: false-positive and alert-fatigue controls

## Goal

Define fatigue ledgers, duplicate suppression, per-service budgets,
false-positive accounting, and operator-burden controls before recommendation
escalation or L3 local sandbox attempts.

## Contract

- Maintain fatigue ledgers with forecast count, recommendation count,
  intervention attempt count, false-positive count, abstention count, operator
  acknowledgement count, duplicate suppression count, fatigue score, fatigue
  budget remaining, and suppression reason.
- Suppress or group duplicate and near-duplicate forecasts within a declared
  horizon.
- Cap recommendations and L3 attempts per system/service/window.
- Require increasing evidence strength as fatigue score rises.
- Count false positives when no incident occurs in the declared horizon and no
  counterfactual benefit is identifiable.
- Report alert burden, duplicate suppression, fatigue budget violations, and
  operator-burden score overall and per system/service/family.

## Acceptance

Fatigue budget violations block recommendation escalation and L3 attempts.
False positives and alert burden remain per-slice release metrics and cannot be
hidden by aggregate utility. Duplicate suppression is deterministic and
replayable.

## Stop Rules

Stop if duplicate forecast storms can page repeatedly, if fatigue budgets can
be bypassed, if aggregate utility hides false positives or alert fatigue, if
per-service metrics are omitted, or if fatigue controls add auth, credentials,
live connectors, production/staging mutation, L4+ authority,
shell/subprocess execution, free-form action execution, or nonzero authority
counters.
