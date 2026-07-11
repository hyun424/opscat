# P120-002: system-level split and near-duplicate prevention

## Goal

Create system-first split manifests and near-duplicate prevention across
incident text, telemetry windows, topology graphs, ontology labels, action
packs, outcomes, generated lineage, and time windows.

## Contract

- Split by system identity before row identity.
- Track split axes for system ID, dataset/source origin, service architecture
  class, topology graph family, telemetry source combination, incident scenario
  family, action family, time window, generated-versus-observed lineage, and
  ontology-mapping version.
- Prevent topology clones, generated variants, replayed faults, prompt
  paraphrases, shared action packs, reused outcome windows, and overlapping
  telemetry windows from crossing split boundaries.
- Freeze split manifests before calibration, thresholding, prompt tuning,
  parser tuning, ontology tuning, OOD cutoff fitting, connector normalization
  tuning, or first unseen score.
- Report duplicate numerator, denominator, threshold, method, blocked pairs,
  manually adjudicated pairs, and unresolved pairs.

## Acceptance

No system crosses development, calibration, and holdout splits. Near duplicates
touching holdout systems are blocked, grouped, or removed from promoted
denominators. Unresolved holdout duplicate risk blocks release. The first score
on a frozen unseen system consumes that split.

## Stop Rules

Stop if row-level splits replace system-level holdouts, calibration or tuning
uses holdout systems, unresolved near duplicates touch holdout systems, or
failed unseen scores can be retuned and counted as a pass.
