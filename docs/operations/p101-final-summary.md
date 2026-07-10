# OpsCat P101 Final Summary — Tool-Using Hypothesis Investigator

P101 converts the earlier report-shaped investigator components into an executed
runtime loop. The agent starts without evidence markers, ranks competing diagnostic
surfaces from the symptom, runs closed read-only tools, incorporates positive or
negative results, and delegates action only after correlated evidence exists.

## Implemented behavior

- 17 registered local diagnostic tools, all read-only and side-effect free.
- Initial packet excludes visible evidence, family, variant, split, required and
  harmful actions, runbook answers, expected outcomes, and lab effect labels.
- Symptom-derived competing tool hypotheses with confidence ranking.
- Maximum three diagnostic calls with negative-result demotion and fallback.
- Evidence-gated delegation to the P100 stateful action agent.
- Equal-state comparison between `direct_visible`, `fixed_tool`, and
  `tool_investigator`.
- Tool accuracy, discovery, efficiency, recovery retention, split, and safety gates.

## Full matrix measured result

```bash
./.venv/bin/python scripts/run_tool_investigation_benchmark.py \
  --seeds 11,29,47 --sample-size 10 \
  --output-json /tmp/opscat-p101-full.json \
  --output-md /tmp/opscat-p101-full.md
```

- Catalog: **52 families / 520 cases**
- Arms: **4,680 trials** across three seeds
- Actual loopback HTTP requests: **118,580**
- Direct-visible stateful recovery: **56.54%**
- Tool-investigator recovery: **56.54%**
- Recovery retention: **100%**
- Fixed-tool ablation recovery: **1.35%**
- Relevant-tool discovery: **100%**
- Top-1 diagnostic tool accuracy: **94.23%**
- Average tool calls per incident arm: **0.9519**
- Unnecessary tool-call rate: **5.45%**
- Development / validation / blind recovery retention: **100% / 100% / 100%**
- Unknown tools, invalid routes, scorer leakage, and investigator collateral: **0**
- Performance and every hard safety gate: **passed**

## Interpretation

P101 does not improve the P100 action policy's recovery ceiling. Instead, it proves
that OpsCat can withhold preassembled evidence, independently choose and execute a
diagnostic, and recover the same cases as the direct-visible agent. The fixed-tool
ablation's 1.35% recovery demonstrates that the result is not produced by merely
calling any tool.

The 94.23% Top-1 result also preserves honest uncertainty: some symptoms require a
second diagnostic surface. Negative results are recorded and cause anti-anchoring
fallback rather than immediate action.

## Boundary and next handoff

Tools are synthetic local reads over the existing case catalog; they do not contact
Grafana, Datadog, Kubernetes, databases, or production systems. Evidence wording and
symptoms remain known vendor-neutral templates, so P101 does not prove generalization
to unseen language or topology.

P102 should evaluate an LLM planner against paraphrased symptoms, hidden service
topologies, distractor tools, and novel evidence combinations while retaining this
same closed tool registry, evidence boundary, policy gate, and causal outcome scorer.
