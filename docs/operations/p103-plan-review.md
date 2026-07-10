# P103 Plan Review

## Approved design

1. Reuse P101's isolated tool/action benchmark instead of creating a second lab.
2. Adapt the P102 provider into P101's `InvestigationDecision` interface.
3. Give the provider only redacted public observation, prior read-only tool
   statuses, remaining budget, and the still-available closed tool catalog.
4. Remove attempted tools from the next catalog; a repeated proposal therefore
   fails closed before execution.
5. On correlated evidence, delegate action selection to P100's deterministic
   evidence policy. The LLM receives no action authority.
6. On malformed output, provider failure, no remaining tool, or exhausted budget,
   escalate without action.
7. Compare direct-visible, fixed-tool, heuristic investigator, and LLM investigator
   from deterministic equal states.
8. Report exact first-tool accuracy and relevant-tool discovery separately from
   end-to-end recovery so a plausible alternate path is not judged by labels alone.

## Acceptance

- A scripted provider recovers after one negative diagnostic and a corrected second choice.
- Repeated, unknown, malformed, and failed-provider proposals execute no tool/action.
- Tool calls never exceed the configured budget.
- Initial provider context contains no family, variant, split, expected tool,
  required action, harmful action, or outcome labels.
- Default verification makes zero external model calls.
- Live NVIDIA mode is explicit opt-in, bounded, and advisory-only.
