# P102 LLM Diagnostic Tool Planner Evaluation

## Outcome

Evaluate an LLM-shaped planner on paraphrased symptoms, opaque topology labels,
distractor tools, and prompt-injection-like text while preserving P101's closed
read-only tool registry and fail-closed execution boundary.

## Tickets

- P102-001 prompt and output schema
- P102-002 closed-tool validation
- P102-003 malformed/unknown-tool fail-closed behavior
- P102-004 deterministic mock provider
- P102-005 opt-in NVIDIA provider reuse
- P102-006 paraphrase perturbations
- P102-007 hidden-topology perturbations
- P102-008 distractor and injection perturbations
- P102-009 provider comparison scorecard
- P102-010 bounded live-provider mode
- P102-011 CLI and reports
- P102-012 tests, docs, and verification

## Stop condition

Default offline evaluation must be deterministic, select only registered read-only
tools, fail closed on every invalid provider response, and pass all safety gates.
Live NVIDIA evaluation remains explicit opt-in and cannot execute a tool or action.
