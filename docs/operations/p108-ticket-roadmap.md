# P108 Prevention Outcome Learner

## Outcome

P108 closes the proactive-prevention loop by learning from whether a P105
forecast and P107 bounded intervention were actually useful. It consumes a
complete raw P107 handoff, independently rebuilds P107 release readiness, writes
an immutable offline outcome ledger, assigns a conservative outcome label,
estimates treatment-versus-control effect, generates review-only policy or
runbook recommendations, and evaluates those recommendations on hidden holdout
replays.

P108 is an offline learner. It adds no staging or production execution path,
does not edit prompts, policy, thresholds, registries, or runbooks, and cannot
grant broader authority.

## Preconditions

- The caller supplies raw P107 audit records, release replay, outcome report,
  fixture-matrix result, verification profile, docs scan, and independent review
  evidence. A copied `release_qualified`, `accepted`, `fresh`, or
  `p108_replay_gate_ready` boolean is never authority.
- P108 independently recomputes the P107 release evidence and validates the
  terminal audit chain, report content hash, replay bindings, exact zero
  authority counters, and fresh independent review.
- P107 evidence must remain local/mock or isolated-harness evidence. A staging
  label, production-like adapter, credential scope, live transport, or network
  evidence invalidates the handoff.
- Treatment and control evidence must be content-bound and comparable before a
  causal outcome can be labeled `prevented` or `delayed`.

## Boundaries

- Offline replay and repo-local fixture evaluation only.
- No auth or session scope.
- No network, shell, subprocess, live connector, cloud, or database access,
  including read-only DB engines, sessions, or queries.
- No production adapters or production mutation.
- No online policy, prompt, registry, threshold, or runbook modification.
- No invocation of P107 executors or any incident action execution path.
- Recommendations are immutable review artifacts with `applied=false`.
- Harmful or false-positive evidence may only recommend a more conservative
  future policy. Less conservative recommendations always require independent
  review and remain unapplied.

## Primary Artifacts

- `app/services/prevention_p108_ingress.py`
- `app/services/prevention_outcome_ledger.py`
- `app/services/prevention_outcome_learner.py`
- `app/services/prevention_counterfactual.py`
- `app/services/prevention_learning_recommendations.py`
- `app/services/prevention_learning_promotion.py`
- `app/services/p108_release_evidence.py`
- `scripts/run_prevention_learning_eval.py`
- `evals/prevention/p108_learning_cases.json`
- `tests/test_prevention_p108_*.py`
- `docs/tickets/p108/README.md`

## Ticket Sequence

1. P108-000 raw P107 ingress pack and independent readiness recomputation.
2. P108-001 immutable cross-phase episode ledger and content hashes.
3. P108-002 conservative outcome labels and temporal cutoff rules.
4. P108-003 treatment/control counterfactual estimator.
5. P108-004 evidence-bound credit assignment.
6. P108-005 false-positive, near-miss, harm, and censored feedback.
7. P108-006 offline threshold/runbook recommendation artifacts.
8. P108-007 holdout replay and generated regression packs.
9. P108-008 promotion gate with hard safety-zero invariants.
10. P108-009 drift report and rollbackable candidate version manifest.
11. P108-010 deterministic fixture matrix and benchmark metrics.
12. P108-011 CLI, docs, targeted verification, and boundary scans.
13. P108-012 release evidence and independent adversarial review.

## Mandatory Outcome Labels

- `prevented`: sufficient comparable control evidence indicates the predicted
  incident occurred or crossed the failure threshold in control while treatment
  remained below it after the intervention.
- `delayed`: both cohorts fail, but treatment crosses the declared incident
  threshold later by the minimum useful delay.
- `unaffected`: comparable evidence shows no material treatment effect.
- `naturally_recovered`: treatment and control recover without a treatment-
  specific effect.
- `harmful`: treatment worsens the primary outcome, breaches a guardrail, or
  causes collateral regression.
- `inconclusive`: evidence is conflicting, incomparable, or causally weak.
- `censored`: the observation horizon or required post-window is incomplete.

`harmful`, `inconclusive`, and `censored` take precedence over optimistic
labels. Missing control evidence can never produce `prevented`.

## Release Gates

1. `p108_ingress_gate`: raw P107 readiness recomputes true without trusting
   submitted readiness booleans.
2. `p108_offline_only_gate`: static and runtime authority counters are exactly
   zero and forbidden imports/calls are absent.
3. `p108_counterfactual_gate`: optimistic labels have comparable control or
   no-action evidence; weak evidence becomes inconclusive/censored.
4. `p108_safety_zero_gate`: harmful promotion, production mutation, unsafe
   auto-action, self-attestation acceptance, replay-forgery acceptance, and
   online policy mutation counts are all zero.
5. `p108_measurability_gate`: per-family denominators and metrics are present;
   aggregate-only success is rejected.
6. `p108_promotion_gate`: a candidate has multiple seeds and time splits,
   improves holdout utility without safety regression, is content-versioned,
   has a rollback pointer, and remains unapplied pending review.

## Independent Review Contract

P108 release review uses exact `schema_version=p108.independent_review.v1` and
requires:

- a non-empty review ID and reviewer ID;
- reviewer role in `code-reviewer`, `architect`, `verifier`, or
  `independent-reviewer`;
- lowercase verdict `pass` (fail/blocked never release);
- RFC3339 UTC `reviewed_at`, evidence timestamp, and explicit maximum age;
- reviewed hashes for the ledger head, P108 release evidence, fixture matrix,
  holdout report, promotion report, recommendation manifest, authority scan,
  docs scan, and P108 release-profile output;
- reviewer identity distinct from the producer identity.

Missing, stale, self-authored, non-passing, wrong-role, or mismatched review
evidence fails closed.

## Promotion Support Rule

Promotion uses six predeclared paired holdout cells: three deterministic seeds
across two disjoint time splits. For each cell:

```text
learning_utility = prevented_precision
                   - unnecessary_intervention_rate
                   - natural_recovery_miscredit_rate
                   - 4 * harmful_intervention_rate
```

Every cell must have positive candidate-minus-baseline utility, the median delta
must be at least `0.03`, no family metric may regress beyond `0.01`, harmful and
hard-safety counts must remain zero, and calibration drift may not increase by
more than `0.01`. Six positive paired signs correspond to a predeclared
one-sided exact sign probability of `1/64`; this is an offline evidence floor,
not a production statistical-significance claim.

## Required Metrics

- prevented-incident precision;
- unnecessary-intervention rate;
- harmful-intervention rate;
- natural-recovery miscredit rate;
- inconclusive and censored rates;
- net avoided impact;
- forecast calibration drift;
- paired holdout learning utility and sign-support evidence;
- per-family treatment effect and sample counts;
- before/after holdout deltas by seed and time split;
- all hard safety counters.

## Required Verification Profile

```bash
bash scripts/verify.sh --profile p108-release
```

The profile must include ingress, ledger, labels, counterfactual, credit,
recommendation, holdout, promotion, drift, fixture matrix, static authority,
CLI, and release-evidence tests. Missing raw handoff artifacts, required fixture
IDs, per-family denominators, or review evidence fail closed.

## Stop Conditions

Stop and do not claim P108 complete if P108 trusts a copied P107 readiness
boolean, accepts a non-terminal or forged replay, labels prevention without
control evidence, directly edits policy/runbooks/prompts, invokes an executor,
hides harmful outcomes in an aggregate score, promotes on one seed/time split,
or grants any new operational authority.

## Post-P108 Boundary

P108 completion proves only deterministic offline learning quality. Live
read-only shadowing, adapter certification, hosted SLOs, multi-tenant isolation,
and any production mutation authority require a separate post-P108 phase.
