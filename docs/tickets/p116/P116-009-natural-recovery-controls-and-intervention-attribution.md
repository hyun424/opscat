# P116-009: natural-recovery controls and intervention attribution

## Goal

Prevent P116 from crediting actions for recoveries that would have happened
without the intervention.

## Contract

- Include matched no-action and natural-recovery controls for every eligible
  scenario family.
- Declare the minimum useful effect window before scoring.
- Compare action recovery time, sustained health, recurrence, and guardrails
  against matched no-action and delayed-intervention evidence.
- Label spontaneous, no-op, rollback-only, reset-only, or wrong-action recovery
  separately from `verified_helpful`.
- Report natural-recovery miscredit rate and wrong-action credit count as hard
  safety-zero gates.

## Acceptance

Tests reject optimistic labels when controls recover within the useful effect
window, when control evidence is missing or incomparable, or when intervention
benefit is smaller than the declared effect size. P116 release requires
natural-recovery miscredit count = 0 and wrong-action credit count = 0.
