# P97 Causal Remediation Benchmark

## Outcome

Measure whether an OpsCat decision **causes** recovery, rather than awarding points for repeating a fixture label. Every candidate is replayed from the same initial state against a no-action control and a human-runbook baseline inside a disposable loopback-only fault lab.

## Tickets

- **P97-001 — Benchmark contract and RED tests**
  - Lock the 120-case taxonomy, hidden-truth boundary, three intervention arms, output contract, and hard safety gates before implementation.
- **P97-002 — Isolated causal fault lab**
  - Run a real loopback HTTP workload with resettable state and fixed allowlisted local actions. Reject arbitrary commands, URLs, and external mutation.
- **P97-003 — Broad operational scenario matrix**
  - Generate 12 operational families × 10 variants with deterministic development, validation, and blind splits.
- **P97-004 — Counterfactual experiment runner**
  - Replay identical case/seed state for `no_action`, `human_runbook`, and `opscat`; collect pre/post workload measurements, action traces, recurrence, and collateral effects.
- **P97-005 — Agent decision boundary**
  - Give selectors visible evidence only. Keep root cause, required actions, harmful actions, and expected outcome outside the selector payload.
- **P97-006 — Outcome and causal scoring**
  - Classify effective, partially effective, no effect, harmful, or unverified; calculate lift over no-action, runbook regret, recovery, recurrence, unnecessary action, and escalation correctness.
- **P97-007 — Hard safety gates**
  - Fail the benchmark on out-of-scope mutation, unknown action execution, unsafe action, false recovery declaration, or data-loss evidence. Do not average safety failures away.
- **P97-008 — Reproducible CLI and reports**
  - Add bounded smoke and full-matrix modes with deterministic seeds and JSON/Markdown evidence.
- **P97-009 — Verification integration**
  - Add targeted tests, docs/release evidence, lint, mypy, coverage, full verification, and repository hygiene checks.

## Stop condition

P97 is complete when the benchmark executes real local HTTP observations and fixed local state-changing actions, compares all three arms from equivalent initial conditions, proves hidden truth is not exposed to the OpsCat selector, produces a 120-case matrix, and passes all hard safety gates. It does **not** claim production remediation effectiveness.
