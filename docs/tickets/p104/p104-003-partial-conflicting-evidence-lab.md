# P104-003 - Partial and Conflicting Evidence Lab

## Goal

Create a fixture-backed P104 lab that extends P101's single expected-tool lab
with partial support, conflicting sources, stale data, unavailable tools,
distractors, duplicate evidence, prompt-injected logs, and natural recovery.

## Tests First

- Seed fixtures cover all required scenario classes.
- Lab output contains public read-only evidence only and excludes scorer truth.
- Prompt-injected content cannot alter route, catalog, tool arguments, or action
  authority.
- Natural recovery during investigation yields observe/escalate semantics, not
  remediation handoff.

## Implementation Notes

- Add `evals/evidence_gap/seed/scenarios.json` with deterministic cases.
- Reuse P101's `DiagnosticTool` catalog and loopback lab boundaries.
- Keep hidden expected sufficiency labels inside benchmark scoring only.

## Acceptance

- Each fixture can produce evidence states for multiple tools, not only one
  expected tool.
- The lab can prove the distinction between "no anomaly observed" and "tool
  unavailable."

## Verification

Run targeted P104 tests plus a small CLI smoke once P104-010 exists.
