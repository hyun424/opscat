# P104-007 - Budget and Fail-Closed Controls

## Goal

Enforce tool-call, provider-call, step, and wall-clock budgets with fail-closed
behavior. Exhaustion should explain the missing evidence and unavailable next
capability.

## Tests First

- Invalid budget bounds fail at construction and CLI parsing.
- Tool budget exhaustion executes no action and returns a gap payload.
- Provider budget exhaustion executes no action and records model-call counters.
- Wall-clock/step budget exhaustion produces `abstain_fail_closed`.
- Repeated provider failures trip fail-closed escalation.

## Implementation Notes

- Keep default budgets small and deterministic for tests.
- Include `remaining_tool_budget`, `remaining_provider_budget`,
  `elapsed_step_count`, and exhaustion reason in the envelope.
- Do not retry unavailable tools blindly.

## Acceptance

- Every budget stop is visible in JSON and Markdown reports.
- Budget stops preserve no-action, no-mutation boundaries.

## Verification

Run targeted P104 tests and CLI invalid-argument tests after P104-010.
