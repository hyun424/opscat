# P116-003: SLO baseline capture and contamination detection

## Goal

Capture healthy pre-fault behavior and block experiments whose starting state
is too noisy or contaminated for causal attribution.

## Contract

- Record latency, error rate, saturation, throughput, queue lag, dependency
  success, and fixture-specific guardrails before fault injection.
- Compute coverage windows and public initial-condition fingerprints before
  any arm-specific mutation.
- Detect unstable baseline health, leftover resources, reused experiment IDs,
  overlapping ports, clock drift, duplicate observations, insufficient warmup,
  and prior fault residue.
- Preserve raw observation hashes so replay can recompute baselines without
  trusting submitted summaries.

## Acceptance

Baseline tests reject contaminated or incomparable arms before the paired
runner starts. Every accepted arm has identical public initial-condition
fingerprint across action, no-action, wrong-action, rollback, and
natural-recovery controls.
