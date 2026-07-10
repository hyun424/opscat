# P101 Plan Review

## Approved design

1. Hide `visible_evidence`, family, variant, split, required actions, harmful
   actions, runbook answers, and lab effect labels from the initial agent packet.
2. Expose only an opaque case ID, symptom, sampled measurements, a closed read-only
   tool catalog, allowed lab actions, and the local boundary.
3. Require at least one diagnostic tool result before any state-changing action.
4. Rank tool-shaped hypotheses from symptom semantics, not case IDs or scorer labels.
5. Feed negative tool results back so the investigator can demote an anchored
   hypothesis and choose another tool, with a maximum of three diagnostic calls.
6. Delegate action choice to the P100 evidence-bounded stateful agent only after a
   diagnostic tool returns correlated evidence.
7. Pass sanitized measurement deltas, never scorer-only action-effect labels, back
   into the action loop.
8. Compare `direct_visible`, `fixed_tool`, and `tool_investigator` from identical
   case/seed fingerprints.

## Adversarial review

### Rejected: giving the agent the expected tool

The expected diagnostic surface is scorer-only. Tool results expose evidence only
after the agent independently chooses a registered tool.

### Rejected: counting a planned tool as tool use

The benchmark records an executed local diagnostic query and its result. A textual
plan alone receives no credit.

### Rejected: acting after only a symptom guess

The coordinator blocks state-changing action until correlated diagnostic evidence
exists in sanitized history.

### Rejected: claiming unseen-language generalization

P101 tests hidden evidence and tool choice over the existing vendor-neutral symptom
catalog. True paraphrase/topology generalization remains a later LLM evaluation and
is not inferred from this deterministic benchmark.

## Acceptance review

- Initial agent calls contain no evidence markers or scorer-only fields.
- Every executed diagnostic tool is registered read-only and has no side effects.
- Negative tool results can cause a different second tool selection.
- Tool evidence supports P100 multi-step action fallback without hidden effect labels.
- Privileged or ambiguous cases preserve zero-mutation escalation.
- Relevant-tool discovery is at least 95%; recovery retention is at least 95%.
- Fixed-tool ablation recovery is lower than the hypothesis investigator.
- Unknown tool/action, route violation, scorer leakage, and collateral hard counters are zero.
