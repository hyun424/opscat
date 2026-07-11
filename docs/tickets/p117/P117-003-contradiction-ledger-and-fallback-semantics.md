# P117-003: contradiction ledger and fallback semantics

## Goal

Make contradictory evidence first-class so the selector can penalize, defer, or
abstain instead of averaging conflicts into unsafe confidence.

## Contract

- Ledger contradiction sets for P114 hypothesis conflicts, evidence timestamp
  conflicts, source conflicts, prerequisite conflicts, contraindication
  conflicts, P116 seed disagreement, natural-recovery ambiguity, and
  calibration drift.
- Attach contradiction IDs to affected actions, evidence requests, utility
  penalties, fallback decisions, and abstention reasons.
- Define thresholds that force deterministic fallback, `investigate_more`, or
  `abstain`.
- Report every changed decision caused by contradiction handling.

## Acceptance

Contradiction RED cases are detected, contradiction-suppression count is 0, and
every threshold-triggered fallback has cited contradiction IDs and deterministic
replay evidence.

## Stop Rules

Stop if contradictions can be hidden by aggregate confidence, omitted from
release reports, or overridden by an LLM proposal.
