# P102 Plan Review

## Approved design

1. The model receives symptom text, sampled public measurements, and a closed tool catalog only.
2. It returns JSON with `route`, `tool`, and `rationale`; no arbitrary arguments or actions are accepted.
3. `inspect` requires one registered read-only tool; `escalate` requires no tool.
4. Malformed JSON, unknown tools, mutation tools, extra actions, or route conflicts fail closed.
5. Default verification uses a deterministic mock provider and performs no network call.
6. NVIDIA is explicit opt-in, bounded by case count, and advisory-only.
7. Perturbation results are tool-selection evidence, not production diagnosis evidence.
8. Provider output cannot execute a tool or action; only the validator can return a closed planning result.

## Acceptance

- Original, paraphrased, opaque-topology, and distractor variants are scored separately.
- Invalid-provider regression cases all escalate without execution.
- Zero unknown-tool execution, mutation, credential, network-default, or action counters.
- Reports clearly distinguish mock from live-provider results.
