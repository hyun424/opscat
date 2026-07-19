# P177 Tickets - Evidence-Seeking LLM Diagnosis

## Goal

Turn diagnosis into an evidence-seeking loop: the LLM proposes hypotheses,
selects bounded read-only evidence requests, revises beliefs, records
contradictions, and stops with a cited diagnosis, abstention, or escalation.

## Non-Goals

- No action execution, auto-approval, production mutation, auth, or payment work.
- No free-form provider queries, shell commands, URLs, or target expansion.

## Dependencies

- P176 sealed multi-service fault matrix and source coverage.
- P172 active investigation patterns and P173 shadow approval boundaries.

## Tickets

1. **P177-001 - Evidence-seeking trace schema.** Define hypothesis, question,
   tool choice, evidence result, contradiction, revision, and stop receipts.
2. **P177-002 - Bounded tool registry.** Expose only observed P176 source-backed
   read tools with allowlisted templates, budgets, freshness checks, and redaction.
3. **P177-003 - Diagnosis policy.** Require source diversity, citation validity,
   uncertainty calibration, and contradiction handling before final diagnosis.
4. **P177-004 - LLM candidate harness.** Compare evidence-seeking LLM, single-pass
   LLM, deterministic baseline, and abstain baseline on identical cases.
5. **P177-005 - Blinded scorer.** Score top-1/top-3 root cause, affected service,
   precursor lead time, citation validity, abstention utility, and unsafe advice.
6. **P177-006 - Release evidence.** Bind traces, prompts, tool registry version,
   model settings, labels, report, and independent review.

## Concrete Deliverables

- `docs/tickets/p177/README.md`, `PRD.md`, and `test-spec.md`.
- P177-owned trace schema, bounded tool registry, diagnosis policy, benchmark
  harness, blinded scorer, and release evidence bundle.
- Hash-bound prompt/model/tool configuration artifacts for every scored episode.

## Architecture

Build a P177 orchestrator around the existing evidence gap investigator and LLM
judgment harness. The policy gate remains deterministic; the LLM can request
evidence and draft diagnosis text but cannot approve actions or widen tools.

## Threat Model

- LLM fabricates evidence or citations.
- Tool registry exposes unobserved providers or free-form queries.
- More tool calls increase false confidence without improving accuracy.
- Prompt or trace leaks hidden labels.

## Acceptance Metrics

- Citation validity = 1.0.
- Unsupported final diagnosis count = 0.
- Use a paired blinded denominator of at least 600 episodes: at least 15 episodes
  for each P176 core fault family and at least 150 healthy, ambiguous, or OOD
  episodes. Every candidate and baseline receives identical episode evidence.
- The comparison baseline is the strongest pre-registered result among the
  single-pass LLM and deterministic baselines; the abstain baseline is reported
  but cannot lower the comparison target.
- On the pre-registered `[0,1]` selective-utility score, evidence-seeking must
  improve over that baseline by at least 0.08 absolute, and the lower endpoint of
  a paired, family-stratified 95% bootstrap CI for the improvement must exceed
  0.03.
- Unsafe action advice and production mutation counts = 0.
- Per-family confidence intervals and calibration curves are reported.
- A scorer isolated from prompt/model/tool implementation owns sealed labels,
  computes all metrics and CIs, signs `independent-scorer-report.json`, and has no
  write path to candidate traces.

## Test Matrix

- Unit: trace schema, budget accounting, source freshness, citation validation.
- Integration: bounded tool execution against P176 recorded/live sessions.
- E2E: blinded diagnosis comparison across all P176 families.
- Adversarial: stale, conflicting, missing, forged, OOD, and label-leak cases.
- Observability: prompt digest, model config, trace hash chain, stop reason.

## Evidence Artifacts

`evals/p177/input/manifest.json`, `evals/p177/output/report.json`,
`evals/p177/output/freeze-manifest.json`,
`evals/p177/output/release-evidence.json`, and
`evals/p177/final-implementation-review.json`, plus
`evals/p177/output/baseline-comparison.json` and
`evals/p177/output/independent-scorer-report.json`.

## Rollback and Stop Conditions

Stop on unsupported citation, hidden-label leakage, free-form tool execution,
credential leakage, production reachability, unsafe action advice, or lower
selective utility than the baseline.

## Promotion Gate

P178 may start only after the 600-episode denominator, absolute effect, CI lower
bound, and independent-scorer gates pass without unsafe advice, false-confidence
regression, unsupported citations, or post-freeze metric changes.
