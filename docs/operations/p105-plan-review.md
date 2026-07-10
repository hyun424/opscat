# P105 Plan Review

## Review Verdict

**APPROVED.** Independent Critic review returned **APPROVE** for commit
`8bb6d74` (`Make P105 gate review reproducible`).

This approval authorizes P105 implementation to proceed to RED tests in ticket
order. It does not authorize implementation shortcuts, P106 work, production
mutation, auth/credential scope, remediation execution, executable action plans,
default external model calls, scorer-truth leakage, or raw LLM confidence as an
execution signal.

## Scope Reviewed

- P105 roadmap: `docs/operations/p105-ticket-roadmap.md`
- P105 ticket set: `docs/tickets/p105/*.md`
- Durable proactive-prevention context:
  `docs/operations/p104-p108-proactive-prevention-master-plan.md`
- Prior review repair commits:
  - `793e671` - initial P105 planning artifact
  - `0dca6c7` - first rejection repair
  - `8bb6d74` - second rejection repair and final approved state

## Rejection Rounds and Resolutions

### Round 1: Rejected after initial P105 planning

The first P105 plan was rejected because it did not yet make the P106 unlock
gate precise enough for implementation. The missing pieces were exact gate rows,
fail-closed denominator semantics, scorer-label isolation, deterministic
incident matching, adapter boundaries for P32/P41 real-derived replay, and
machine-checkable placement of P24 legacy advisory fields.

Commit `0dca6c7` resolved the rejection by adding:

- the P106 gate table with formulas, numerators, denominators, thresholds,
  split IDs, family/source scope, and pass/fail/unevaluable status;
- fail-closed handling for missing numerator, denominator, service-day,
  incident, family, or abstention counts;
- zero-positive supported-family semantics that keep P106 locked unless support
  is withdrawn or fixture coverage is added;
- scorer-only fixture labels and public-packet stripping requirements;
- one-to-one incident matching semantics, duplicate-alert burden, and abstention
  handling;
- P32/P41 adapter limits that preserve read-only/local boundaries and prevent
  action plans, policy handoffs, credentials, downloads, live API calls, or
  production mutation paths;
- exact compatibility markers:
  `compatibility.legacy_advisory=true`,
  `prevention_plan.legacy_advisory=true`, nested
  `action_execution_enabled=false`, and
  `compatibility.p106_required_for_execution=true`.

### Round 2: Rejected after first repair

The second review rejected the plan because clean clones could not reproduce the
review context while the P104-P108 master plan lived only in ignored `.omx`
state. It also found that the real-derived useful-lead-time transfer gate used
an order-insensitive absolute comparison even though the intended gate was a
directional drop from held-out to real-derived performance.

Commit `8bb6d74` resolved the rejection by:

- tracking the P104-P108 master plan at
  `docs/operations/p104-p108-proactive-prevention-master-plan.md`;
- updating `docs/operations/p104-plan-review.md` to cite the tracked master
  plan instead of ignored `.omx` state;
- adding the tracked master-plan anchor to the P105 roadmap;
- changing useful-lead-time transfer to the directional formula
  `held_out_useful_lead_time_rate - real_derived_useful_lead_time_rate <= 0.10`;
- requiring both held-out and real-derived rates to use
  `useful_true_positive_count / true_positive_count` for the same supported
  family and split;
- making missing numerators, denominators, split/source identity, missing
  `actual_positive_count`, or zero `true_positive_count` unevaluable and
  therefore P106-locking.

## Final Verified Gates

The approved P105 plan requires every P106 unlock row to be present and passing:

1. Held-out Brier improvement over P24 globally and for each supported family
   with positives.
2. Held-out ECE improvement over P24 globally and for each supported family with
   positives.
3. Useful lead-time rate `>= 0.80` for every supported family with positives.
4. Zero-positive supported families marked unevaluable and P106-locking unless
   removed from `supported_families`.
5. False alerts per service-day `<= 0.25` globally and `<= 0.50` per supported
   family.
6. Abstention rate `<= 0.20` globally and `<= 0.30` per supported family.
7. Real-derived useful-lead-time transfer using the directional drop formula,
   with real-derived rate still `>= 0.80`.
8. Real-derived false-alert transfer with at most `<= 0.10` absolute increase
   and still within the false-alert threshold.
9. Safety boundary counters showing no auth, no production mutation, no
   remediation execution, no executable action plan, and no default external
   model calls.

Reviewer-attributed verification for the final approved state:

```text
git diff --check
rg stale ignored master-plan refs in docs
rg contradictory useful-lead-time absolute/drop wording
verified docs/operations/p105-plan-review.md absent before approval
```

Runtime source tests were not run for the review commits because the reviewed
changes were planning documentation only.

## Reviewer Independence and Read-Only Status

The Critic review was independent of the plan-writing commits and evaluated the
tracked planning artifacts from a read-only review posture. The reviewer did not
modify source code, tests, or planning files as part of the verdict. Required
changes were returned as rejection findings, then resolved in follow-up commits
before the final APPROVE outcome.

## Implementation Authorization

P105 is authorized to proceed to RED tests for:

1. P105-000 forecast/action split and P24 compatibility adapter.
2. P105-001 typed forecast schema.
3. P105-002 leakage-resistant time-ordered split.
4. P105-003 deterministic P24 baseline.
5. P105-004 multi-signal feature builder.
6. P105-005 calibration and uncertainty.
7. P105-006 missing-feature and distribution-shift abstention.
8. P105-007 optional NVIDIA rationale guard.
9. P105-008 per-family lead-time and false-alert benchmark.
10. P105-009 real-derived shadow transfer gate.
11. P105-010 model card and release verification.
12. P105-011 release integration and P106 gate lock.

P106 remains locked until the exact P105 release gate passes with populated
denominators, supported-family coverage, real-derived transfer evidence, and
hard-zero safety counters.
