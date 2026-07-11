# P111 evidence-driven RCA accuracy plan

## Objective

Improve root-cause service and fault-family judgment without weakening P110's
truth isolation, response replay, provenance binding, or zero-execution
authority.

## Baseline

The frozen P110 repetition-5 result is development-contaminated because its
errors have been inspected:

- service Top-1: 20/25 (0.80)
- service Top-3: 23/25 (0.92)
- fault accuracy: 13/25 (0.52)
- evidence precision: 140/140 (1.00)
- disk: 0/5; loss: 0/5

P111 MUST NOT describe a gain on repetition 5 as blind generalization.

## Data governance

- Repetition 5: frozen contaminated baseline; diagnostic comparison only.
- Repetition 1: development and prompt/feature ablation.
- Repetition 2: validation and one-time configuration selection.
- Repetition 3: blind acceptance set; no tuning after unsealing its score.
- Repetition 4: untouched reserve for later independent confirmation.
- Candidate packets never contain repetition, source path, root service, or
  fault labels.

The selected P111 configuration is frozen by a manifest containing the model,
prompt schema, decoding parameters, implementation hash, source hash, and
candidate-packet hash before repetition 3 is scored.

## Design

1. Derive candidate-visible diagnostic views from the same sealed evidence:
   per-service/per-metric pre/post/delta, robust cross-service ranks, relative
   changes, and supporting evidence IDs.
2. Ask the model to perform an explicit hypothesis loop inside one response:
   localize service, compare all five fault families, seek contradictory
   evidence, then return the existing strict P110 output schema.
3. Teach operational distinctions without case-specific examples:
   resource saturation, memory growth, storage pressure, transport delay, and
   packet loss are competing hypotheses rather than interchangeable symptoms.
4. Keep all actions advisory-only and re-use P110 strict validation and raw
   response replay.

## Acceptance gates

- Blind repetition-3 service Top-1 >= 0.84 and fault accuracy >= 0.68.
- Blind disk and loss accuracy each >= 0.60.
- Service Top-3 >= 0.92 and evidence precision >= 0.95.
- Positive paired deltas versus a P110-prompt baseline on the same cases.
- Two-run exact service/fault agreement >= 0.80 before any release claim.
- Zero truth leaks, invalid citations, harmful actions, executed actions,
  provider errors, duplicate outputs, missing outputs, and unknown outputs.
- Confidence calibration is reported; score gains cannot hide increased
  confident-error rate.
- `release_qualified` remains false without cryptographic independent review.

## Stop conditions

Stop tuning after the repetition-2 selection decision. If repetition 3 misses
the gates, report the failure and preserve repetition 4 instead of tuning on
repetition 3.
