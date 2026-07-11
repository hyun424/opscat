# P121 Proactive Prevention Roadmap / PRD

## Objective

P121 implements a local/mock/sandbox proactive prevention phase for OpsCat. It
turns leading indicators into calibrated, evidence-bound, counterfactual
prevention decisions before an incident crosses the declared impact threshold.

P121 remains exact-zero authority. Its only execution path is a registered
disposable local sandbox fixture guarded by deterministic approval, durable
WAL/hash-chain recovery, idempotency, CAS payload matching, leases, validation,
and rollback receipts. It creates no production access, deployment permission,
credential scope, connector authority, or production/staging mutation path.

## Product Claim

P121 may claim only local/mock/sandbox proactive prevention readiness after
frozen unseen temporal and system holdouts, calibrated abstention, prevention
utility measurement, harm accounting, crash/replay proof, and independent
review.

P121 may not claim production-safe autonomous prevention, production
readiness, live connector operation, production mutation, credentialed action
authority, auth coverage, operator replacement, or production incident
reduction.

## Source Context

- P119 supplies the closed-loop response spine: detection, diagnosis,
  evidence acquisition, deterministic approval, local execution,
  validation/rollback, causal attribution, recurrence learning, crash recovery,
  frozen evaluation, and exact-zero nonlocal authority counters.
- P120 supplies cross-system generalization controls: source governance,
  system-level splits, near-duplicate prevention, telemetry normalization, OOD
  detection, calibration, abstention, frozen first-score evaluation,
  per-system metrics, and independent review.
- P104-P108 supply proactive prevention concepts: calibrated pre-failure
  forecasts, preventive planning, local/mock canaries, immutable episode
  ledgers, counterfactual treatment/control estimates, avoided impact, harmful
  intervention rate, alert burden, and conservative learning.

## Non-Authority Boundary

Every P121 artifact preserves these invariants:

- auth is deferred;
- users, sessions, RBAC, OIDC/SSO, production identity, credentials, secrets,
  and production approval provenance are out of scope;
- P121 maximum authority is L3 local/mock/sandbox;
- L0 observes and collects local/mock evidence;
- L1 recommends prevention with evidence and risk;
- L2 performs dry-run or static preflight only;
- L3 may execute only registered disposable local sandbox fixture actions;
- production and staging mutation are forbidden;
- live connector calls, connector writes, Kubernetes/cloud/database/network
  mutation, online policy writes, shell/subprocess execution, free-form action
  execution, LLM command execution, and L4+ actions are forbidden;
- forecast confidence alone is never action authority;
- local/mock/sandbox prevention evidence cannot be promoted as production
  safety evidence.

Every release evidence bundle must report these counters, and all must be
exactly zero:

```text
auth_context_count
credential_scope_count
secret_material_count
live_connector_call_count
connector_write_call_count
shell_execution_count
subprocess_execution_count
kubernetes_mutation_count
cloud_mutation_count
database_mutation_count
network_mutation_count
filesystem_mutation_outside_artifact_count
online_policy_write_count
staging_mutation_count
production_mutation_count
l4_plus_action_count
freeform_action_execution_count
llm_command_execution_count
authority_escape_count
unapproved_intervention_count
evidence_bypass_count
rollback_missing_execution_count
```

## Prevention Protocol

P121 evaluates the proactive path in eight layers:

1. Leading indicators from local fixtures, frozen telemetry snapshots,
   P120-normalized telemetry, and P119 recurrence records.
2. Forecast horizons with lead time, expiry, uncertainty, calibration,
   abstention, OOD status, and required evidence before action.
3. Evidence acquisition before any recommendation, dry-run, or L3 attempt.
4. Counterfactual prevention decisioning against action, no-action,
   investigate-more, and safe-null baselines.
5. False-positive, alert-fatigue, intervention-cost, and operator-burden
   controls before escalation.
6. Deterministic approval for every L3 local sandbox attempt.
7. Validation, rollback, causal attribution, harm accounting, and recurrence
   reduction learning.
8. Frozen temporal/system holdout evaluation, crash/replay proof, release
   evidence, and independent review.

Allowed decision routes are `prevent_l1_recommend`, `prevent_l2_dry_run`,
`prevent_l3_local_sandbox`, `investigate_more`, `no_action`, `escalate`, and
`abstain_fail_closed`.

## Leading Indicators and Forecast Horizons

Leading indicators must be hash-bound, time-bounded, and free of future
labels, hidden scorer fields, post-intervention telemetry, post-incident
hindsight, or consumed holdout data. Indicators with stale telemetry, missing
data, unresolved duplicate lineage, ambiguous system identity, or weak source
quality must route to `investigate_more` or abstain.

Every forecast must state the failure mode, incident family, probability,
calibrated probability, calibration bucket, confidence interval, horizon start,
horizon end, minimum useful lead time, expiry, expected impact, uncertainty
reasons, OOD status, abstention status, required evidence before action,
model/rule version, frozen config hash, and artifact hash.

Intervention eligibility requires positive useful lead time, an unexpired
horizon, acceptable calibration, acceptable OOD status, no unresolved
contradiction, all required evidence present, and deterministic approval.

## Evidence Before Action

P121 requires evidence acquisition before any preventive route. Evidence
requests are local/mock read-only, frozen-taxonomy only, and hash-bound.
Missing, stale, contradictory, post-cutoff, unhashable, or nonlocal evidence
routes to `investigate_more` or `abstain_fail_closed`.

Evidence-bypass attempts are release blockers and must increment
release-blocking counters. No intervention may proceed from forecast
confidence alone.

## Counterfactual Prevention

Every decision compares action, no-action, investigate-more, and safe-null
baselines. Utility includes avoided impact, useful delay, rollback cost,
false-positive cost, alert-fatigue cost, intervention harm, operator burden,
and uncertainty penalty.

Natural recovery, weak treatment/control comparability, censored horizons,
ambiguous attribution, rollback recovery, and false prevention credit cannot be
counted as prevented. Harm overrides optimistic utility and blocks promotion.

## False-Positive and Alert-Fatigue Controls

Each system and service maintains a fatigue ledger with forecast count,
recommendation count, intervention attempt count, false-positive count,
abstention count, operator acknowledgement count, duplicate suppression count,
fatigue score, and fatigue budget remaining.

P121 must suppress duplicate or near-duplicate forecasts within a declared
horizon, cap recommendations and L3 attempts per service/window, require
stronger evidence as fatigue rises, count false positives when horizons pass
without incident or identifiable counterfactual benefit, and prevent aggregate
utility from hiding per-service fatigue or harm.

## Validation, Rollback, and Causal Attribution

Validation windows, rollback probes, pre-intervention baselines, and
post-intervention windows must be declared before L3 execution. Failed,
harmful, ambiguous, or collateral-regression outcomes trigger local rollback
when rollback is available.

Outcome labels include `prevented`, `delayed`, `unaffected`,
`naturally_recovered`, `harmful`, `false_positive`, `inconclusive`,
`censored`, `rollback_recovered`, and `aborted_fail_closed`.

Causal attribution reports treatment/control comparability, natural recovery,
avoided impact, useful delay, harm, confidence, rejected credit reasons, and
recurrence delta. Recurrence reduction must use matched pre/post windows and
confidence intervals; a single aggregate count is not enough.

## Frozen Temporal/System Evaluation

P121 freezes time, system, service, topology, incident-family, action-family,
source lineage, ontology version, calibration config, OOD threshold, fatigue
config, utility threshold, seed, evaluator hash, and reviewer input before
first holdout score.

The frozen manifest stores raw visible inputs and scorer-only hidden truth.
It must not store pre-scored pass/fail, forecast-correct, abstention-correct,
harm, false-positive, rollback, duplicate-effect, or utility booleans. The
evaluator derives predictions and outcomes from raw inputs, then compares them
with hidden truth. System split separation, non-overlapping temporal windows,
and near-duplicate fingerprints are enforced before any metric is reported.

The first score consumes a holdout even on failure. Near duplicates,
replayed faults, topology clones, generated variants, shared action packs,
shared outcome windows, and overlapping telemetry windows cannot cross split
boundaries. Retuning on consumed holdouts is forbidden.

## Metrics and Release Gates

Release evidence reports denominators, confidence intervals, per-system
slices, per-service slices, per-horizon slices, per-family slices, and
aggregate values for:

- forecast precision, recall, useful lead-time rate, and false-positive rate;
- calibration ECE and Brier score;
- abstention precision/recall and OOD-abstention correctness;
- investigate-more correctness and evidence acquisition yield;
- prevention utility against no-action, investigate-more, and safe-null
  baselines;
- avoided impact, useful delay, harm, rollback rate, rollback success rate,
  false-prevention credit rate, and recurrence reduction;
- alert burden, duplicate suppression rate, fatigue budget violations, and
  operator-burden score;
- crash/replay consistency, idempotency duplicate-effect count, and exact-zero
  authority counters.

Aggregate improvement cannot hide harmful intervention, rollback failure,
authority drift, alert-fatigue budget violation, calibration failure,
abstention failure, or per-slice degradation.

## Phases

- Phase 0 - Complete: documentation, test spec, plan review, and ticket handoff.
- Phase 1 - Complete: leading indicator and forecast horizon contracts.
- Phase 2 - Complete: evidence acquisition before intervention.
- Phase 3 - Complete: counterfactual prevention utility and baselines.
- Phase 4 - Complete: false-positive and alert-fatigue controls.
- Phase 5 - Complete: deterministic approval and L0-L3 local/sandbox intervention.
- Phase 6 - Complete: validation, rollback, causal attribution, and recurrence
  reduction.
- Phase 7 - Complete: frozen unseen temporal/system evaluation.
- Phase 8 - Complete: crash/replay, release evidence, docs, and independent review.

## Tickets

1. `[complete] P121-001` - leading indicator and forecast horizon contracts
2. `[complete] P121-002` - evidence acquisition before intervention
3. `[complete] P121-003` - counterfactual prevention utility and baselines
4. `[complete] P121-004` - false-positive and alert-fatigue controls
5. `[complete] P121-005` - deterministic approval and L0-L3 local/sandbox intervention
6. `[complete] P121-006` - validation, rollback, causal attribution, and recurrence reduction
7. `[complete] P121-007` - frozen unseen temporal/system evaluation
8. `[complete] P121-008` - docs, test spec, release evidence, crash/replay, and independent review

## Stop Conditions

Stop before implementation, evaluation, release, or claim promotion if any
requirement would add auth, credentials, secrets, production identity,
credential scopes, live production/staging connectors, connector write paths,
production/staging mutation, Kubernetes/cloud/database/network mutation,
online policy writes, shell/subprocess action paths, L4+ authority, free-form
action prose, LLM-generated commands, intervention without evidence,
forecast-only authorization, missing validation/rollback plans, post-holdout
retuning, hidden false positives, hidden alert fatigue, hidden harmful
interventions, hidden rollback failures, aggregate-only metrics, natural
recovery credit, rollback recovery credit, self-review, nonzero authority
counters, or claims beyond local/mock/sandbox proactive prevention readiness.
