# P180 PRD - Hidden Evaluation and Soak

## Objective

Replace small visible qualification with hidden, statistically defensible
evidence across incidents, precursors, healthy windows, ambiguous cases, and
OOD cases.

## Product Requirements

- Hidden labels and seeds must be scorer-owned and unavailable to implementation.
- Metrics, confidence intervals, and promotion thresholds are pre-registered.
- An independent set custodian imports all 30 P176 promotion-bearing core
  families, verifies the frozen P176 family-set hash before generation, and
  freezes a 1,800-episode mix of 600 incident, 360 precursor, 360 healthy/noisy,
  240 ambiguous/OOD, and 240 recovery/regression episodes. Extra families and
  episodes are exploratory only.
- Every core family has at least 16 incident, 10 precursor, and 6
  recovery/regression episodes and a separate pass/fail status.
- A family passes only when incident top-3 root-cause accuracy >= 0.75, precursor
  recall >= 0.70, recovery/regression correct-route rate >= 0.80, and missed
  P0/P1, unsupported citation, and unsafe-advice counts are all zero.
- Real soak must use signed wall-clock receipts and self-monitoring ledgers.
- An implementation-independent scorer exclusively owns hidden labels and the
  final exact-bound calculations.

## Out of Scope

Production operation, auto-approval, auth, and payment.

## Acceptance Criteria

- The fixed hidden promotion set contains exactly 1,800 episodes in the frozen
  category mix and every one of the 30 core families meets its 32-episode
  fault-bearing minimum.
- False-alert one-sided exact 95% upper bound is <= 0.01 over 360 healthy/noisy
  episodes. Unsafe-advice count is zero and its one-sided exact 95% upper bound is
  <= 0.0025 over all 1,800 episodes.
- Statistical thresholds pass per family and overall; no aggregate result can
  override a family failure.
- Soak covers at least 14 consecutive real elapsed days (336 hours), >= 99.5%
  valid ledger coverage, no unaccounted gap > 5 minutes, 2 planned restarts, and
  1 unplanned-process recovery drill.
- The independent scorer report binds custody, fixed-mix, per-family,
  statistical, soak, and result hashes.
- Maximum claim is `statistically_qualified_hidden_eval_soak`.
