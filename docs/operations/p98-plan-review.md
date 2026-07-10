# P98 Plan Review

## Approved design

1. Reuse P97 as the causal execution oracle instead of building a second simulator.
2. Keep hidden truth out of the selector and treat selector output as untrusted data: parse a tiny JSON contract, allow only
   observed action names, and convert malformed output into escalation with no action.
3. Keep model access opt-in and key-gated. The default and all verification paths are
   deterministic and network-free.
4. Compare selectors independently from the same case/seed matrix; aggregate only
   after reporting hard safety failures and blind-split results.
5. Report recovery, durable recovery, causal lift, action precision, harmful action,
   unverified outcomes, escalation correctness, and regret against the curated human
   runbook. Never collapse this into one quality number.

## Adversarial review

### Rejected: judging explanations as success

Rationale and confidence are useful audit fields, but selector quality is determined
by measured post-action state and durability from P97.

### Rejected: giving the model family, variant, required action, or expected outcome

Those fields remain scorer-only. Prompt construction is tested to prevent accidental
truth leakage.

### Rejected: allowing the LLM to execute tools directly

The LLM can propose only an action name. P97's closed in-memory lab remains the sole
executor, and unknown actions are blocked by the existing hard gate.

### Rejected: production fallback on model failure

Timeout, missing key, malformed JSON, unknown route, and unknown action all fail closed
to escalation. They never silently become an automatic production action.

## Acceptance review

- At least three selectors are included in comparison output.
- Blind split is present in every selector result.
- Prompt/context contains only the public P97 observation contract.
- A malformed provider response yields `escalate` with zero executable actions.
- NVIDIA mode is explicit opt-in and never default verification.
- All selector hard safety gates pass; no selector can average away a safety violation.
