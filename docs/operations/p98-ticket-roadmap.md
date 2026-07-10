# P98 Selector Comparison and Blind Causal Evaluation

## Outcome

Compare the current deterministic selector, a conservative observation-only ablation,
and an opt-in LLM selector against the same P97 causal lab. The benchmark must show
whether a model improves measured recovery and operator-like judgment, not merely
whether it produces plausible explanations.

## Tickets

- **P98-001 — Comparison contract and RED tests**
  - Define selector interface, evidence-only prompt boundary, scorecard, blind-split metrics, and hard safety gates before implementation.
- **P98-002 — Evidence-only LLM decision adapter**
  - Add strict JSON parsing, route/action allowlisting, prompt-injection resistance, confidence, and fail-closed behavior.
- **P98-003 — Deterministic mock LLM and ablation selectors**
  - Provide reproducible local selectors so quality can be measured without a model key or network.
- **P98-004 — Optional NVIDIA selector**
  - Add an explicit key-gated OpenAI-compatible NVIDIA adapter. It may advise only; P97 remains the only action executor and stays loopback/mock-only.
- **P98-005 — Multi-selector comparison runner**
  - Run each selector on identical cases/seeds and report overall, blind, per-family, safety, escalation, harmful-action, and human-runbook-regret metrics.
- **P98-006 — Operational case coverage**
  - Preserve the 12-family/10-variant matrix and add checks for natural recovery, missing/conflicting telemetry, compound faults, privileged scope, and ineffective first actions.
- **P98-007 — CLI, reports, and verification**
  - Add bounded smoke/full matrix commands, JSON/Markdown artifacts, targeted tests, lint/type checks, and release evidence.

## Stop condition

P98 is complete when at least three selectors are compared from identical initial
states, the selector receives no hidden truth, blind-split causal metrics are emitted,
malformed or unsafe model output fails closed, and all hard safety gates pass. An
LLM score is not treated as production evidence or operator replacement approval.
