# P104-006 - Strict LLM Gap Proposal

## Goal

Add an optional strict provider that can propose a missing evidence gap and next
read-only tool. The model cannot decide sufficiency, authorize actions, add
tools, add arguments, or override deterministic gates.

## Tests First

- Malformed JSON, extra fields, unknown tools, action fields, shell text,
  credential requests, invalid routes, repeated tools, and provider exceptions
  fail closed.
- Provider context includes only public observation, sanitized evidence states,
  requirement summaries, closed catalog, attempted tools, and remaining budget.
- Default tests and CLI mode perform zero model/network calls.
- Live-provider mode, if added, is explicit opt-in and bounded by case count,
  tool-call budget, provider-call budget, and timeout.

## Implementation Notes

- Follow P102's `LLMToolPlanner` validation style.
- Accepted provider routes should be limited to `inspect_next` and
  `escalate_gap`.
- Deterministic sufficiency remains authoritative after any proposal.

## Acceptance

- Provider output never executes a tool directly and never executes an action.
- Provider action authority is always false in reports.

## Verification

Run targeted P104 tests with mock, malformed, repeating, failing, and
live-shaped providers.
