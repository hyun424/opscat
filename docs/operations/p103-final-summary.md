# P103 Final Summary — Multi-step LLM Diagnostic Episode

## Delivered

- A history-aware adapter from P102's strict provider contract into P101's
  isolated diagnostic/action loop.
- Negative-result replanning with attempted tools removed from the next catalog.
- Positive-evidence handoff to P100's deterministic action policy; the provider
  receives no action authority.
- A configurable 1–10 read-only tool-call budget and repeated-tool prevention.
- Fail-closed handling for provider errors, malformed output, unknown/repeated
  tools, invalid routes, and exhausted budgets.
- Equal-state comparison of direct-visible, fixed-tool, heuristic-investigator,
  and LLM-investigator arms.
- Separate exact first-tool, relevant-tool discovery, and measured recovery metrics.
- A deterministic offline default plus explicit opt-in NVIDIA evaluation.

## Deterministic full-catalog result

The default mock provider ran all **520 cases** from 52 operational families,
producing **2,080 reported comparison trials**. Internally, two P101 benchmark
runs executed 3,120 arms so the heuristic and LLM adapters could be measured
against identical deterministic control construction.

- First-tool accuracy: **94.23%**.
- Relevant-tool discovery: **100%**.
- LLM-investigator recovery: **56.15%**.
- Heuristic-investigator recovery: **56.15%**.
- Recovery retention versus heuristic: **100%**.
- Fixed-tool recovery: **1.35%**.
- Recovery after a wrong first tool: **77.78%**.
- Repeated-tool executions, budget violations, state mismatches, provider action
  executions, and production mutations: **0**.

The mock provider reconstructs the P101 heuristic from the prompt packet. It is a
deterministic regression oracle, not evidence of external-model intelligence.

## NVIDIA 52-family live-provider result

The bounded live run selected one obvious case from each of the 52 families. It
produced **208 reported comparison trials** and **67 external model decisions**.

- First-tool accuracy: **76.92%**.
- Relevant-tool discovery: **98.08%**.
- Average read-only tool calls: **1.2885**.
- Episodes that replanned after a negative result: **12**.
- LLM-investigator recovery: **76.92%**.
- Heuristic-investigator recovery: **76.92%**.
- Recovery retention versus heuristic: **100%**.
- Recovery after a wrong first tool: **75%**.
- Fixed-tool recovery: **1.92%**.
- Hard safety gate: **PASS**.
- The provider executed zero actions.

One `duplicate_processing` episode exhausted all three distinct read-only tools
without finding the scorer-selected surface and escalated without further action.
No tool repeated, no call crossed the configured budget, and the provider executed
zero actions. P100's closed synthetic policy performed any subsequent lab action.

## Interpretation

P102 showed that a model's first answer was imperfect. P103 shows why an agentic
loop matters: a wrong first diagnostic can be corrected by observing a negative
result and choosing a different tool. On this sample, multi-step investigation
raised relevant-tool discovery from 76.92% first-choice accuracy to 98.08% and
retained the heuristic's measured recovery rate.

## Boundary

The live sample uses synthetic symptoms and synthetic read-only tool results in an
isolated `127.0.0.1` fault lab. It does not prove production diagnosis quality,
customer-environment safety, connector correctness, or unattended remediation.
The external model can choose a closed read-only diagnostic only; it cannot select,
parameterize, approve, or execute remediation actions.

## Next capability

P104 should evaluate **uncertainty and evidence sufficiency** before remediation:
calibrated confidence, competing hypotheses, explicit contradiction checks,
abstention thresholds, and a requirement that proposed root cause/action claims
cite the diagnostic observations that support and contradict them.
