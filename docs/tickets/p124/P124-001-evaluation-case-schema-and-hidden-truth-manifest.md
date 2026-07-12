# P124-001: evaluation case schema and hidden-truth manifest

## Goal

Define the future schema for judgment-quality cases and hidden-truth labels.

## Contract

- Separate model-visible evidence from hidden truth labels.
- Include case hashes, split labels, permitted outputs, abstention, and
  evaluator-only truth metadata.
- Reject filenames, IDs, logs, or metadata that leak hidden truth.

## Acceptance

Future evaluators can score judgments without exposing hidden truth to the
judgment path.

## Stop Rules

Stop if hidden truth is model-visible, split metadata is missing, or case
manifests cannot be hash-bound.

