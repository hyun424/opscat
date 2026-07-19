# P178 Test Spec

## Claims Under Test

1. Precursors are detected at a useful lead time.
2. Healthy/noisy windows do not trigger excessive prevention proposals.
3. Prevention recommendations are evidence-bound and policy-bound.
4. Counterfactual benefit is reported without action-authority inflation.

## Matrix

- Schema tests for precursor labels and prevention decisions.
- Unit tests for eligibility, abstention, escalation, and fatigue metrics.
- Blinded campaigns over precursor, incident, healthy, noisy, OOD, and natural
  recovery windows.
- Paired baseline tests against frozen deterministic-precursor and
  P177-diagnosis-only outputs, scored by the isolated scorer.
- Negative tests for stale, single-source, contradictory, unsupported, and
  forged evidence.

## Pass Gates

- `precursor_recall_at_lead_time >= 0.80`.
- `blinded_window_count >= 600`.
- `actionable_precursor_window_count >= 300`.
- `healthy_noisy_natural_recovery_window_count >= 300`.
- `prevention_eligible_family_count >= 15` and
  `min_precursor_windows_per_eligible_family >= 15`.
- `comparison_baseline == max(deterministic_precursor_baseline,
  p177_diagnosis_only_baseline)`.
- `net_prevention_utility_absolute_lift >= 0.05` and
  `net_prevention_utility_lift_paired_stratified_bootstrap_95ci_lower > 0.01`.
- `healthy_false_prevention_rate <= 0.01` and
  `healthy_false_prevention_one_sided_exact_95ub <= 0.01`.
- If `healthy_noisy_natural_recovery_window_count == 300`, then
  `false_prevention_count == 0`; for a larger frozen denominator, the observed
  count must satisfy both rate gates without post-run denominator growth.
- `independent_scorer_report_valid == true` and
  `post_freeze_metric_change_count == 0`.
- `unsupported_prevention_proposal_count == 0`.
- `auto_approval_count == 0`.
- `production_mutation_count == 0`.
