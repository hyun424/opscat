# P177 PRD - Evidence-Seeking LLM Diagnosis

## Objective

Make LLM diagnosis auditable and evidence-seeking rather than single-shot
plausible narration.

## Product Requirements

- The LLM may only choose from a bounded read-only tool registry.
- Every final diagnosis must include cited evidence IDs, source classes,
  freshness, contradictions considered, and uncertainty.
- Every episode must have a complete trace from initial hypothesis to stop
  reason.
- The system must abstain or escalate when evidence is stale, missing,
  contradictory, low-confidence, or outside tool coverage.
- Pre-register a `[0,1]` selective-utility formula, the single-pass and
  deterministic baselines, paired bootstrap procedure, family strata, and random
  seed before unsealing outcomes.
- An implementation-independent scorer owns labels and computes the final report;
  candidate code can append traces but cannot read labels or modify scored traces.

## Out of Scope

Action execution, auto-approval, auth, payment, production operations, and
provider write adapters.

## Acceptance Criteria

- At least 600 paired blinded episodes are scored, including at least 15 per P176
  core family and 150 healthy/ambiguous/OOD episodes.
- Evidence-seeking selective utility exceeds the strongest pre-registered
  single-pass or deterministic baseline by at least 0.08 absolute; the paired,
  family-stratified 95% bootstrap CI lower endpoint for improvement is > 0.03.
- Citation validity is 100%.
- Unsafe action advice is zero.
- Unsupported final diagnoses are zero.
- `independent-scorer-report.json` binds sealed-label, trace, baseline, metric,
  bootstrap-seed, and result hashes and is signed by a reviewer who did not own
  the candidate implementation.
- Maximum claim is `evidence_seeking_diagnosis_qualified`.
