# P116 Plan Review

## Decision: accepted as a lab-only measurement phase

P116 is accepted only as a controlled, disposable laboratory for producing
measured paired outcome records. It does not grant action authority and does
not replace P118 canary execution. Its value is the causal evidence needed by
P115 and later action-selection work.

## Required Corrections Incorporated

- Outcome quality is judged by measured SLO movement, rollback, recurrence,
  collateral damage, and replay, not by textual action similarity.
- Action, no-action, wrong-action, rollback, and natural-recovery controls are
  mandatory paired arms.
- Natural recovery and no-op recovery cannot be credited to an intervention.
- Initial-condition fingerprints must prove comparable arms before scoring.
- Resets are a release gate, not best-effort cleanup.
- Randomized arm order and repeated seeds are required to expose order effects
  and variance.
- Crash recovery, idempotency, concurrency, and orphan cleanup are part of the
  lab claim rather than operational polish.
- Frozen acceptance and independent replay are required before P116 outcomes
  can feed P115 scoring.
- Production authority, credentials, external clusters, cloud mutation, and
  live remediation remain exactly zero.

## Adversarial Concerns

- A lab can accidentally become an executor if action plans are modeled too
  close to production APIs. P116 therefore uses lab-only action receipts and
  explicit authority counters.
- Helpful-looking actions can be spurious when fixtures naturally recover. P116
  blocks optimistic labels without matched natural-recovery controls.
- Wrong actions can appear successful when reset or rollback masks the outcome.
  P116 separates action outcome, rollback outcome, and reset outcome.
- Aggregate pass rates can hide unsafe families. P116 requires per-family
  denominators and safety-zero counters.
- Reproducibility can be faked by trusting submitted summaries. P116 requires
  independent replay from raw observations.

## Residual Risks

- Local fixtures may not capture production complexity; P116 should claim only
  isolated lab causality.
- Docker and local Kubernetes-compatible runtimes may have platform variance;
  repeated-seed variance reporting is required.
- Some P115 scenario families may be hard to reset safely; those families stay
  non-release-counting until reset evidence reaches 1.0.
- Future P118 authority work must re-review every assumption because P116
  explicitly has no production authority.

## Stop Conditions

Stop before implementation or release if any requirement pressures P116 to use
production credentials, external mutable infrastructure, broad network access,
unbounded shell execution, or live remediation authority. Stop release if reset
success, rollback success, or natural-recovery attribution is incomplete.
