# P116-006: randomized order and repeated-seed variance analysis

## Goal

Detect order effects, flaky fixture behavior, and unstable action outcomes
before any P116 record is considered release-counting.

## Contract

- Predeclare randomization seed and arm schedule before execution.
- Repeat eligible scenario cells across multiple deterministic seeds.
- Report qualitative label stability and numeric variance for primary SLO,
  recovery time, collateral damage, recurrence, and rollback duration.
- Flag order-only wins, warm-cache artifacts, lingering-resource effects,
  noisy baselines, and platform-specific variance.
- Keep unstable families non-release-counting until variance is bounded.

## Acceptance

Variance reports identify every scenario family, fixture version, seed set, and
excluded cell. Release gates fail if helpful-action claims depend on execution
order or one lucky seed.
