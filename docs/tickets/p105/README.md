# P105 - Calibrated Failure Forecast Engine

P105 converts P104-qualified evidence plus P24/P25 trend windows into typed,
calibrated forecasts of concrete failure modes. It preserves the existing
P24/P25 payload through a compatibility adapter, but marks legacy prevention
plans as advisory only until P106 compiles a policy-valid action plan.

Boundary: tests-first; no auth; no production mutation; no remediation
execution; no default external model calls; no scorer-truth leakage; no
future-window leakage; raw LLM confidence never drives execution.

## Tickets

- [P105-000 - Forecast/action split and P24 compatibility adapter](p105-000-forecast-action-split-compatibility-adapter.md)
- [P105-001 - Typed forecast schema](p105-001-typed-forecast-schema.md)
- [P105-002 - Leakage-resistant time-ordered split](p105-002-leakage-resistant-time-ordered-split.md)
- [P105-003 - Deterministic P24 baseline](p105-003-deterministic-p24-baseline.md)
- [P105-004 - Multi-signal feature builder](p105-004-multi-signal-feature-builder.md)
- [P105-005 - Calibration and uncertainty](p105-005-calibration-and-uncertainty.md)
- [P105-006 - Missing-feature and distribution-shift abstention](p105-006-missing-feature-distribution-shift-abstention.md)
- [P105-007 - Optional NVIDIA rationale guard](p105-007-optional-nvidia-rationale-guard.md)
- [P105-008 - Per-family lead-time and false-alert benchmark](p105-008-per-family-lead-time-false-alert-benchmark.md)
- [P105-009 - Real-derived shadow transfer gate](p105-009-real-derived-shadow-transfer-gate.md)
- [P105-010 - Model card and release verification](p105-010-model-card-release-verification.md)
- [P105-011 - Release integration and P106 gate lock](p105-011-release-integration-p106-gate-lock.md)

## Phase Acceptance

- Forecast output is typed, calibrated, and action-free.
- Existing P24/P25 callers can still consume forecast payloads through the
  adapter, with `prevention_plan` marked `legacy_advisory`.
- Train/calibration/test splits are time ordered and incident-group isolated.
- Deterministic P24 baseline metrics are published with the same denominators as
  P105 metrics.
- Missing critical features, unavailable evidence, low coverage, and
  distribution shift abstain or stay conservative.
- Reports include precision, recall, PR-AUC, Brier, ECE, lead time, false
  alerts/service-day, and abstention rate with exact denominators.
- P106 remains blocked unless held-out calibration and real-derived shadow
  transfer thresholds pass.
