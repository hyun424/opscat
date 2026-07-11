# P116-008: frozen lab benchmark and independent replay

## Goal

Freeze the P116 acceptance benchmark and require independent replay from raw
observations before lab outcomes can feed P115 scoring.

## Contract

- Freeze scenario registry, fixture manifests, action catalog subset, random
  seeds, split assignments, scorer configuration, and acceptance thresholds.
- Separate development fixtures from frozen acceptance fixtures and detect
  exact or near-duplicate overlap.
- Release evidence binds hashes for raw observations, canonical outcome
  records, metrics, reset/rollback receipts, authority scan, and verification
  output.
- Independent replay recomputes labels and metrics without trusting submitted
  outcome labels or copied release booleans.
- Self-review, stale hashes, mismatched artifacts, and aggregate-only metrics
  fail closed.

## Acceptance

Replay consistency is at least 0.99, all required release hashes match, every
metric includes per-family denominators, and independent review finds no
authority escape or causal-attribution blocker.
