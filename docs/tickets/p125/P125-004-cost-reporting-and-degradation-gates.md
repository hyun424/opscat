# P125-004: cost reporting and degradation gates

## Goal

Define local cost and quality-degradation gates for long-running shadow runs.

## Contract

- Report CPU, memory, storage, runtime, queue depth, retry counts, and
  per-event cost.
- Flag judgment-quality degradation against P124 metrics where available.
- Reject cloud-billing or production-cost claims.

## Acceptance

Future reports describe local resource cost and degradation without claiming
production SLO readiness.

## Stop Rules

Stop if cost evidence hides hardware context, resource leaks, or unbounded
retry behavior.

