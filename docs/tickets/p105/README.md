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
- [P105-012 - Release qualification floors and mode semantics](p105-012-release-qualification-floors-mode-semantics.md)
- [P105-013 - Deterministic source-record row generation](p105-013-deterministic-source-record-row-generation.md)
- [P105-014 - Partition, coverage, and safety-conformance hardening](p105-014-partition-coverage-safety-conformance-hardening.md)
- [P105-015 - Release documentation, P24 parity, and authority lock](p105-015-release-docs-p24-parity-authority-lock.md)
- [P105-016 - Release-qualified evidence contract](p105-016-release-qualified-evidence-contract.md)
- [P105-017 - Deterministic local materializer](p105-017-deterministic-local-materializer.md)
- [P105-018 - Locked smoke artifact](p105-018-locked-smoke-artifact.md)
- [P105-019 - Qualified artifact generation](p105-019-qualified-artifact-generation.md)
- [P105-020 - Parity, partition, coverage, and isolation](p105-020-parity-partition-coverage-isolation.md)
- [P105-021 - Reproducibility and tamper tests](p105-021-reproducibility-and-tamper-tests.md)
- [P105-022 - Independent review and full verification](p105-022-independent-review-full-verification.md)

## Phase Acceptance

- Forecast output is typed, calibrated, and action-free.
- Existing P24/P25 callers can still consume forecast payloads through the
  adapter, with `compatibility.legacy_advisory=true`,
  `prevention_plan.legacy_advisory=true`, nested action
  `action_execution_enabled=false`, and
  `compatibility.p106_required_for_execution=true`.
- Train/calibration/test splits are time ordered and incident-group isolated.
- Deterministic P24 baseline metrics are published with the same denominators as
  P105 metrics.
- Missing critical features, unavailable evidence, low coverage, and
  distribution shift abstain or stay conservative.
- Reports include precision, recall, PR-AUC, Brier, ECE, lead time, false
  alerts/service-day, and abstention rate with exact denominators.
- `smoke_only` and tiny-N runs can verify wiring but always keep
  `release_qualified=false` and `p106_unlocked=false`.
- Missing, null, empty, or unknown mode metadata normalizes to
  `smoke_only_missing_mode`, which is smoke-only and default-false for both
  `release_qualified` and `p106_unlocked`. Current committed P105 fixture files
  have no release-qualified mode metadata and are smoke evidence only.
- Release-qualified evidence passes the anti-tiny-N held-out and real-derived
  per-family floors, source diversity, service-day coverage, deterministic
  source-record provenance, outcome-neutral partitioning, and
  safety-conformance diagnostic semantics.
- Service-day exposure is the union of row coverage intervals per
  split/family/service/source scope; overlapping intervals are merged before
  false-alert burden is computed.
- P32/P41/P44 release rows use canonical source tuples and the roadmap's
  P32/P41/P44-to-P105 family mapping; P44 is explicit opt-in only and does not
  count until materialized, redacted, source-hashed, and assigned to
  `real_derived_shadow`.
- Intentional leaked diagnostics are private-harness only. Public and release
  artifacts may publish violation metadata and hash-safe references only; raw
  leakage in a public/release artifact fails closed.
- P106 remains blocked unless the exact P106 gate table passes: held-out
  Brier/ECE improve over P24, useful lead-time rate is `>= 0.80` for every
  supported family with positives, zero-positive supported families are
  `unevaluable`, false alerts/service-day and abstention ceilings pass, and
  real-derived P32/P41 transfer stays within tolerance.
- G006 release-qualified evidence planning adds a deterministic local/offline
  materializer sequence, separate locked smoke and qualified artifacts,
  canonical six-field provenance, P24 parity, merged coverage, outcome-neutral
  partitions, incident isolation, reproducibility/tamper tests, independent
  review, and full verification. These are planning requirements until their
  RED tests and implementation land.
- The G006 repair plan also requires source-availability preflight manifests,
  separate P44-disabled negative and reviewed-local P44 positive commands,
  private scorer-label ledgers, per-row reconstructable P24 parity manifests,
  anti-clone checks, and label-tamper tests before any release-qualified claim.
