# P124 Adversarial Test Specification

This specification is a planning handoff for future P124 implementation.
Implementation is pending. It does not require source-code edits, test edits,
runtime access, credentials, human-subject collection, staging access,
production access, or mutation during this documentation turn.

## Contract and Authority

- Reject credentials, secrets, live connector calls, production/staging target
  strings, mutation fields, shell/subprocess action fields, free-form action
  prose, LLM command text, and L4+ action requests.
- Require exact-zero authority counters for every future P124 evidence bundle.
- Reject claims that evaluation quality proves production autonomy or operator
  replacement.

## Hidden Truth and Leakage

- Detect hidden-truth leakage into prompts, evidence packets, model-visible
  metadata, filenames, case IDs, logs, reports, or replay receipts.
- Require split manifests, holdout labels, hash-bound cases, and reviewer-only
  truth access.

## Human Baseline

- Detect missing reviewer count, missing reviewer role, missing adjudication,
  missing inter-rater agreement, stale baseline, self-reviewed baseline,
  conflict ignored, and baseline promoted without denominator.
- Require human baseline reports to include uncertainty and slice coverage.

## Scoring

- Detect aggregate-only scores, missing denominator, missing confidence
  interval, cherry-picked cases, consumed holdout reuse, missing abstention
  scoring, missing safety score, and unsupported causal precision claims.
- Require per-slice metrics and failure analysis.

## Named RED Cases

- `hidden_truth_leakage`
- `human_baseline_self_review`
- `aggregate_only_quality_claim`
- `missing_denominator`
- `missing_confidence_interval`
- `operator_replacement_claim`
- `production_accuracy_claim`
- `consumed_holdout_reuse`
- `nonzero_authority_counter`

## Verification Profile

Future implementation must provide targeted P124 verification for hidden-truth
isolation, human baseline protocol, adjudication, scoring, calibration, slice
metrics, failure analysis, claim controls, and exact-zero authority counters.
Documentation completion does not require those tests to exist yet.

