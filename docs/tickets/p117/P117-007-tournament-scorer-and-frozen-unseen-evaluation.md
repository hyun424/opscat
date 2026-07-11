# P117-007: tournament scorer and frozen unseen evaluation

## Goal

Evaluate deterministic, NVIDIA proposal, safe-null, and abstain-heavy selectors
on frozen unseen episodes with identical denominators and replayable metrics.

## Contract

- Freeze episode registry, P114/P115/P116 manifests, evidence taxonomy, utility
  thresholds, calibration method, deterministic config, NVIDIA config, split
  assignment, and near-duplicate filters before scoring.
- Score unseen once; the split is consumed after first score regardless of
  outcome.
- Report per-family, per-action-family, per-label, per-split, and aggregate
  metrics with numerator, denominator, nullable value, interval, and threshold.
- Include disagreement reports for every changed decision and fallback reason.
- Independent replay recomputes decisions and metrics from frozen inputs rather
  than trusting submitted labels or release booleans.

## Acceptance

Frozen unseen replay consistency is >= 0.99, every selector uses identical
denominators, aggregate-only reports fail, near-duplicate leakage is 0, and no
unseen tuning occurs after first score.

## Stop Rules

Stop if unseen labels influence configuration, denominators differ across
selectors, replay trusts submitted labels, or a failed unseen run is retuned
into a pass.
