# P121-003: counterfactual prevention utility and baselines

## Goal

Define lead-time-aware expected prevention utility over action, no-action,
investigate-more, and safe-null baselines with natural-recovery controls and
harm accounting.

## Contract

- Compare candidate prevention actions against no-action, investigate-more,
  and safe-null baselines on identical denominators.
- Include avoided impact, useful delay, rollback cost, false-positive cost,
  alert-fatigue cost, operator burden, intervention harm, and uncertainty
  penalty in utility.
- Track counterfactual refs, natural-recovery control refs, treatment/control
  comparability, confidence, censored horizons, and rejected credit reasons.
- Preserve outcome labels for prevented, delayed, unaffected,
  naturally recovered, harmful, false positive, inconclusive, censored,
  rollback recovered, and aborted fail-closed cases.
- Prevent harm, weak comparability, natural recovery, censored horizons,
  rollback recovery, or ambiguous attribution from being promoted by aggregate
  utility.

## Acceptance

Prevention utility is positive only when counterfactual evidence is
identifiable, harm does not dominate, natural recovery does not explain the
outcome, and baseline comparisons are complete. Harmful and ambiguous outcomes
remain denominator-visible and block promotion even when aggregate utility
looks favorable.

## Stop Rules

Stop if no-action, investigate-more, or safe-null baselines are omitted; if
natural recovery, rollback recovery, false positives, censored outcomes, or
ambiguous attribution can receive prevention credit; if harm is hidden by
aggregate metrics; or if utility scoring creates auth, credentials, live
connector authority, production/staging mutation, L4+ authority,
shell/subprocess execution, free-form action execution, or nonzero authority
counters.
