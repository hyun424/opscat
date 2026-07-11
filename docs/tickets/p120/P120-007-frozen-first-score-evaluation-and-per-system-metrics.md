# P120-007: frozen first-score evaluation and per-system metrics

## Goal

Freeze the complete evaluation bundle and score unseen systems exactly once,
with per-system metrics, replay receipts, authority scans, and failure records.

## Contract

- Freeze source manifests, split manifests, near-duplicate reports,
  normalization versions, ontology versions, OOD thresholds, calibration
  configs, selector configs, prompt/model/parser settings, baseline configs,
  seeds, thresholds, evaluator hashes, release thresholds, and reviewer inputs.
- Score each unseen system once; first score consumes the split.
- Record failed unseen scores as negative evidence, not tuning data.
- Report metrics aggregate and per system, dataset, telemetry source,
  architecture, incident family, and action family.
- Include denominators, confidence intervals, replay receipts, authority scans,
  baseline deltas, and nullable metrics.

## Acceptance

Release metrics include at least 3 systems, 5 telemetry source classes, 20
scenario families, and unseen-system diagnosis/action quality degradation <= 15
percentage points or explicit failure evidence. Stale hashes, tampering,
self-review, aggregate-only metrics, missing denominators, missing replay
receipts, or authority drift block release.

## Stop Rules

Stop if post-score tuning can be counted as a pass, consumed holdouts can be
rescored for promotion, freeze manifests are stale or tampered, system-level
denominators are missing, confidence intervals are omitted, or any authority
counter is nonzero.
