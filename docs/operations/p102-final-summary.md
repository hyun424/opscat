# P102 Final Summary — LLM Diagnostic Tool Planner Evaluation

## Delivered

- A provider-neutral planner that accepts only `inspect` or `escalate` JSON.
- An allowlist of 17 read-only diagnostic tools inherited from P101.
- Strict schema, type, route, tool, and unexpected-field validation.
- Fail-closed behavior for malformed output, provider errors, unknown tools,
  arguments, actions, commands, URLs, credentials, and mutation attempts.
- Four variants per case: original, paraphrased, opaque topology, and an
  untrusted prompt-injection-like distractor.
- A deterministic offline provider plus an explicit opt-in NVIDIA adapter with
  a 30-second request timeout and one retry.
- JSON/Markdown reports and release verification integration.

## Measured results

### Deterministic fixture baseline

- 52 operational families and **208 decisions**.
- Valid output: **100%**.
- Exact-tool accuracy: **94.23%**.
- Zero unsafe tools, network calls, or action executions.
- Accuracy was 94.23% on each of the four perturbation types.

This is a regression oracle built from the existing P101 heuristic. It verifies
the evaluation and safety plumbing; it is not evidence of LLM intelligence.

### NVIDIA live-provider sample

- Model: repository-configured NVIDIA NIM model.
- 12 distinct operational families and **48 live decisions**.
- Valid exact-schema output: **100%** after prompt/schema tightening.
- Exact-tool accuracy: **83.33%** (40/48).
- Per-perturbation accuracy: **83.33%** for original, paraphrased, opaque
  topology, and prompt-injection-like distractor variants.
- Zero unknown/unsafe tool proposals and zero tool/action executions.

The eight exact-label misses were concentrated in application-runtime,
natural-recovery, and compound-failure cases. The model often selected
`platform.inspect` or `metrics.query` where the scorer expected a single
different first diagnostic. Some are plausible alternatives, but they remain
misses under this benchmark's intentionally strict exact-tool metric.

## What this proves

- A real external LLM can be evaluated against the same closed tool contract.
- Prompt and topology perturbations do not grant execution authority.
- Invalid provider output and provider outages become safe escalation.
- Model quality is measurable separately from action/remediation quality.

## What this does not prove

- The 12-family live sample does not prove production generalization.
- Exact-tool accuracy does not prove root-cause correctness or recovery.
- Synthetic descriptions do not replace real incident traces or operator labels.
- No live tool was executed, so this does not prove production diagnosis latency,
  access safety, or remediation effectiveness.

## Next capability

P103 should connect the validated LLM planner to a **bounded multi-step diagnostic
episode** in the isolated lab: select one read-only tool, consume its negative or
positive result, revise hypotheses, stop on budget, and compare end-to-end recovery
against the P101 heuristic. The scorer must report both strict exact-tool accuracy
and outcome-based diagnostic utility so plausible alternative paths are not judged
only by a single label.
