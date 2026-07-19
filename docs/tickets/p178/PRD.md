# P178 PRD - Prevention

## Objective

Show that OpsCat can detect actionable precursors and recommend bounded
preventive responses without causing excessive false prevention or fatigue.

## Product Requirements

- Precursor windows and lead-time thresholds are pre-registered.
- Prevention output includes evidence IDs, confidence, expected benefit,
  possible harm, and abstention/escalation reason.
- Healthy and noisy windows remain first-class denominators.
- Counterfactual scoring must separate observed outcomes from agent-visible
  evidence.
- Pre-register the net-prevention-utility formula, deterministic-precursor and
  diagnosis-only baselines, paired CI procedure, and family strata.
- Independent scoring must be label-sealed and organizationally or process-wise
  separate from prevention-policy implementation.

## Out of Scope

Automatic prevention action, production operations, auth, and payment.

## Acceptance Criteria

- At least 600 blinded windows are scored: 300 actionable precursor and 300
  healthy/noisy/natural-recovery, with at least 15 precursor windows per eligible
  family and at least 15 eligible families.
- Precursor recall is >= 0.80 at the frozen lead time.
- Net prevention utility improves by >= 0.05 absolute over the strongest frozen
  deterministic-precursor or P177-diagnosis-only baseline, and the paired,
  family-stratified 95% bootstrap CI lower endpoint is > 0.01.
- The false-prevention point rate and one-sided exact 95% upper bound are each <=
  0.01 on the 300+ negative windows. At exactly 300 windows, false-prevention
  count (`false_prevention_count`) must be zero; any nonzero allowance requires a
  larger denominator frozen before scoring and must still pass both bounds.
- Counterfactual benefit is reported with confidence intervals by family.
- No unsupported prevention proposal or unsafe action advice.
- The signed independent scorer report validates label, baseline, metric, window,
  CI-seed, and result hashes with zero post-freeze metric changes.
- Maximum claim is `bounded_prevention_shadow_qualified`.
