# P104 Plan Review

## Review Verdict

**APPROVED.** Independent Critic review returned **OKAY/approved** with no
required plan changes before execution.

This approval authorizes P104 to proceed to RED tests for the Evidence Gap
Investigator. It does not authorize implementation shortcuts, production
mutation, auth/credential scope, or action execution by provider output.

## Scope Reviewed

- P104 roadmap: `docs/operations/p104-ticket-roadmap.md`
- P104 ticket set: `docs/tickets/p104/*.md`
- P104-P108 prevention plan:
  `docs/operations/p104-p108-proactive-prevention-master-plan.md`
- Baseline code boundaries:
  `app/services/tool_using_hypothesis_investigator.py`,
  `app/services/llm_tool_planner_evaluation.py`,
  `app/services/llm_diagnostic_episode.py`, and
  `app/services/stateful_incident_investigator.py`

## Verified Requirements

1. P104 is correctly scoped as an evidence sufficiency layer between P103's
   read-only diagnostic loop and P100's deterministic action boundary.
2. The shared decision envelope is the right first ticket because P105-P108 must
   consume one evidence shape instead of inventing phase-local contracts.
3. The plan preserves the closed P101 read-only diagnostic catalog and extends
   the current lab beyond one expected tool versus empty evidence.
4. The optional LLM path remains advisory: it may propose a missing evidence gap
   or next read-only tool, but cannot declare sufficiency, authorize actions, add
   tools, request credentials, or override deterministic gates.
5. Sufficiency hard gates require fresh critical evidence, no unresolved
   contradiction, adequate telemetry, no unavailable critical capability, and
   explicit evidence-to-claim citations before P100 handoff.
6. Escalation and abstention payloads must explain missing, stale,
   contradicted, duplicated, unavailable, or unsafe evidence without requesting
   production access.
7. Benchmarks must compare P104 against P103 and fixed-tool baselines from equal
   initial states and must prove that valid absence differs from telemetry/tool
   unavailability.

## Code Anchors

- P101 closed catalog and read-only tool metadata:
  `app/services/tool_using_hypothesis_investigator.py:52-70`.
- P101 current synthetic lab limitation, where only the expected tool returns
  evidence:
  `app/services/tool_using_hypothesis_investigator.py:247-268`.
- P102 strict planner validation and fail-closed provider handling:
  `app/services/llm_tool_planner_evaluation.py:53-63` and
  `app/services/llm_tool_planner_evaluation.py:202-243`.
- P103 advisory provider packet with `read_only_tools_only=true`,
  `production_mutation_enabled=false`, and `action_authority=false`:
  `app/services/llm_diagnostic_episode.py:73-89`.
- P103 positive-evidence handoff boundary that P104 must strengthen:
  `app/services/llm_diagnostic_episode.py:48-50`.
- P100 downstream deterministic blocks for privileged scope, low telemetry, and
  conflicting evidence:
  `app/services/stateful_incident_investigator.py:67-109`.

## Test Evidence

The independent Critic review reported the targeted P101-P103 regression suite
as passing:

```text
22 passed
```

I did not rerun that suite while creating this document. Treat the result above
as Critic-attributed evidence for plan approval, not as a fresh local test run.

## Accepted Risks and Boundaries

- P104 may initially increase abstentions because a single correlated anomaly is
  no longer sufficient for action handoff.
- P104 does not prove production diagnostic quality; its default evidence is
  local/mock, deterministic, network-free, and action-disabled.
- Optional NVIDIA/live-provider checks remain explicit opt-in, bounded, and
  advisory-only after deterministic gates pass.
- P104 must not add auth, credentials, connectors, production mutation,
  mutating diagnostics, online learning, threshold auto-tuning, or scorer-truth
  leakage.
- P105 remains blocked until P104 benchmark evidence proves contradiction
  blocking, scorer-truth isolation, critical-evidence citations, and the
  distinction between valid absence and unavailable/no-data states.

## Authorization

P104 is approved to proceed to RED tests in ticket order:
P104-000 through P104-010. The first executable work should lock the shared
decision envelope and validation failures before any GREEN implementation.
