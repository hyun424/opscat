# P178 Tickets - Prevention and Pre-Incident Intervention

## Goal

Qualify prevention decisions before incidents become outages. P178 detects
precursors, recommends bounded preventive responses, and scores counterfactual
benefit without granting new mutation authority.

## Non-Goals

- No production mutation.
- No unsupervised prevention action.
- No auth, payment, billing, or tenant administration work.

## Dependencies

- P177 evidence-seeking diagnosis and precursor labels.
- P176 multi-service healthy and precursor windows.

## Tickets

1. **P178-001 - Precursor taxonomy.** Freeze precursor definitions, lead-time
   windows, expected prevention classes, and non-actionable noisy signals.
2. **P178-002 - Prevention policy profile.** Define deterministic eligibility,
   abstention, escalation, and counterfactual response classes.
3. **P178-003 - Counterfactual evaluator.** Score avoided incident probability,
   false prevention cost, fatigue, and evidence sufficiency without executing.
4. **P178-004 - Supervised prevention drill.** Optionally run human-approved
   staging prevention drills, separately counted from auto-approval.
5. **P178-005 - Regression and safety suite.** Prove healthy-window prevention
   proposals, stale evidence, and unsupported citations fail closed.
6. **P178-006 - Release evidence.** Bind precursor labels, policies, outcomes,
   fatigue metrics, and independent review.

## Concrete Deliverables

- `docs/tickets/p178/README.md`, `PRD.md`, and `test-spec.md`.
- P178-owned precursor taxonomy, prevention policy profile, counterfactual
  evaluator, optional supervised drill runner, and release evidence bundle.
- Fatigue, benefit, false-prevention, and abstention reports by fault family.

## Architecture

Reuse P177 traces for precursor reasoning and P173 shadow approval semantics for
counterfactual prevention decisions. Action execution remains outside the P178
qualification claim unless manually supervised and separately labeled.

## Threat Model

- Prevention creates more operator fatigue than incidents avoided.
- Correlation is mistaken for a causal precursor.
- Counterfactual benefit is overclaimed.
- Preventive action class expands beyond reviewed policies.

## Acceptance Metrics

- Precursor recall >= 0.80 at the pre-registered lead time.
- Score at least 600 blinded windows: at least 300 actionable precursor windows
  and 300 healthy/noisy/natural-recovery windows. Every prevention-eligible
  family has at least 15 precursor windows and at least 15 families are eligible.
- Compare against the strongest pre-registered deterministic-precursor or
  P177-diagnosis-only baseline on identical windows. Net prevention utility must
  improve by at least 0.05 absolute, with a paired family-stratified 95% bootstrap
  CI lower endpoint > 0.01.
- Healthy/noisy/natural-recovery false-prevention point rate <= 0.01 and its
  one-sided exact 95% upper bound <= 0.01.
- At the minimum 300 negative-window denominator this exact-bound gate requires
  `false_prevention_count == 0`; a nonzero count may pass only if a larger
  pre-frozen denominator still satisfies both the point and exact upper bounds.
- Unsupported prevention proposal, unsafe advice, auto-approval, and production
  mutation counts = 0.
- Counterfactual benefit and false-prevention cost are reported per family.
- A scorer independent of prevention-policy implementation owns sealed outcomes,
  computes utility/recall/false-prevention CIs, and signs the final scorer report.

## Test Matrix

- Unit: precursor schema, policy eligibility, fatigue scoring.
- Integration: P177 trace reuse and P176 source freshness.
- E2E: precursor/healthy/noisy/collateral campaigns.
- Adversarial: natural recovery, stale evidence, false correlation, OOD signals.
- Observability: prevention ledger, counterfactual report, operator burden.

## Evidence Artifacts

`evals/p178/input/manifest.json`, `evals/p178/output/report.json`,
`evals/p178/output/freeze-manifest.json`,
`evals/p178/output/release-evidence.json`, and
`evals/p178/final-implementation-review.json`, plus
`evals/p178/output/baseline-comparison.json` and
`evals/p178/output/independent-scorer-report.json`.

## Rollback and Stop Conditions

Stop on unsupported prevention proposal, hidden-label leakage, policy widening,
unsafe advice, elevated healthy false-prevention rate, or any production
reachability.

## Promotion Gate

P179 may start only after the fixed denominators, baseline lift, CI lower bound,
false-prevention upper bound, independent scorer, and operator-fatigue gates pass.
