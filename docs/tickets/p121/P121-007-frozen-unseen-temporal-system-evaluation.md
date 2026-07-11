# P121-007: frozen unseen temporal/system evaluation

## Goal

Define frozen evaluation for unseen temporal and system holdouts with
calibration, abstention, prevention utility, harm, fatigue, recurrence,
rollback, crash/replay, and exact-zero authority metrics.

## Contract

- Freeze split manifests for systems, services, time windows, topologies,
  sources, incident families, action families, generated/observed lineage,
  ontology versions, calibration configs, OOD thresholds, fatigue configs,
  utility thresholds, seeds, evaluator hashes, release thresholds, and reviewer
  inputs before first score.
- Prevent systems, services, topology clones, generated variants, replayed
  faults, shared action packs, shared outcome windows, source lineage, and
  overlapping telemetry windows from crossing development, calibration, and
  holdout boundaries.
- Treat the first score as consuming the holdout split, pass or fail.
- Record failed unseen scores as negative evidence, not tuning data.
- Report metrics overall and per system, service, horizon bucket, incident
  family, action family, source lineage, and authority-sensitive slice.

## Acceptance

Near duplicates touching holdouts block release or remove the affected split
from promoted denominators. Calibration, abstention, OOD, fatigue, utility,
prompt/parser/ontology, and threshold settings are not tuned after first
holdout score. Release metrics include denominators, confidence intervals,
replay receipts, authority scans, and exact-zero counters.

## Stop Rules

Stop if row-level splits replace temporal/system holdouts, if holdouts are
used for calibration or tuning, if consumed holdouts can be rescored as a pass,
if unresolved near duplicates touch holdouts, if aggregate metrics hide
per-slice failure, or if evaluation introduces auth, credentials, live
connectors, production/staging mutation, L4+ authority, shell/subprocess
execution, free-form action execution, or nonzero authority counters.
