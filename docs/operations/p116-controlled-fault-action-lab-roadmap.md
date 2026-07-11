# P116 Controlled Fault/Action Lab Roadmap

## Objective

P116 builds the isolated laboratory that P115 needs before action scoring can
claim causal outcome quality. It measures paired outcomes for the same initial
state under action, no-action, wrong-action, rollback, and natural-recovery
controls.

P116 is not an execution-authority phase. It creates only disposable local
experiment contracts, resettable fixtures, deterministic replay evidence, and
verifier-owned outcome records. It may not touch production systems,
credentials, cloud accounts, Kubernetes clusters outside the disposable lab,
or live customer data.

## Source Context

- P115 defines the incident/action/outcome ontology, hidden evaluator contract,
  and counterfactual scoring requirement. P116 supplies measured paired
  outcomes that P115 can later score.
- P106 showed how treatment/control comparability must be proven from a shared
  initial-condition fingerprint before any metric is credited.
- P107/P108 canary and learning work is local/mock/offline authority only; P116
  must not inherit any executor authority from those phases.
- P109 remediation-import rules reject natural recovery and no-op credit. P116
  makes those controls first-class lab arms.
- P114 release discipline requires frozen acceptance splits, replay receipts,
  aggregate-only release evidence, and independent review before stronger
  claims.

## Non-Authority Boundary

Every P116 artifact must preserve these invariants:

- no production mutation, production adapter, credential, auth/session scope,
  cloud account, external Kubernetes context, database credential, or customer
  environment;
- no shell, network, subprocess, container, or orchestration action is executed
  by documentation work in this phase;
- future harness execution is confined to explicitly disposable local Docker or
  disposable local Kubernetes-compatible environments;
- any candidate action is a lab action against a fixture, never an OpsCat
  production remediation;
- approval records are lab metadata only and cannot unlock P118 or later
  authority;
- unsafe, irreversible, secret-bearing, broad-blast-radius, or unresettable
  actions are represented only as rejected cases.

## Lab Model

Each experiment is an immutable tuple:

```text
experiment_id
scenario_id
fault_family
fixture_version
seed
initial_condition_fingerprint
fault_injection_receipt
arm_name
action_plan_id
action_execution_receipt
observation_window
rollback_receipt
reset_receipt
outcome_record
replay_receipt
```

The comparable arms for one paired cell must share fixture version, seed,
pre-fault baseline, fault injection receipt, public initial state, and
initial-condition fingerprint. Arm name, hidden oracle labels, selected action,
and expected outcome are excluded from the fingerprint.

## Scenario Families

P116 should cover the P115 matrix with resettable local fixtures:

- CPU saturation;
- memory pressure and leak;
- disk full and high latency storage;
- network delay, packet loss, and socket exhaustion;
- deploy/config regression;
- dependency timeout and error injection;
- database pool saturation;
- queue backlog and dead-letter pressure;
- DNS resolution failure;
- certificate expiry or invalid chain;
- quota and rate-limit exhaustion;
- cache poisoning, stale cache, and eviction storm;
- traffic skew and hot partition.

Each family must have at least one helpful action, one no-action arm, one
wrong-action arm, and one natural-recovery control. Families without a safe
reset path remain non-release-counting until P116-007 proves cleanup and
orphan handling.

## Ticket Sequence

1. P116-001 disposable experiment contract.
2. P116-002 deterministic fault injectors and resettable fixtures.
3. P116-003 SLO baseline capture and contamination detection.
4. P116-004 paired action/no-action/wrong-action runner.
5. P116-005 outcome metrics and causal labels.
6. P116-006 randomized order and repeated-seed variance analysis.
7. P116-007 crash recovery, idempotency, concurrency, and orphan cleanup.
8. P116-008 frozen lab benchmark and independent replay.
9. P116-009 natural-recovery controls and intervention-attribution checks.

## Required Outcome Labels

- `verified_helpful`: action arm improves the primary SLO versus matched
  no-action and natural-recovery controls by the declared effect size, with no
  guardrail breach and successful post-window verification.
- `verified_harmful`: action worsens the primary SLO, breaches collateral
  guardrails, extends recovery, or prevents reset/rollback.
- `no_effect`: action is statistically indistinguishable from matched
  no-action and natural-recovery controls.
- `wrong_action_recovered`: wrong-action arm recovers only because the fault
  naturally resolves or because reset/rollback restored the system; never
  credited as helpful.
- `naturally_recovered`: no-action or delayed-intervention control recovers
  within the observation window without treatment-specific effect.
- `rollback_verified`: rollback restores the baseline health window and leaves
  no orphan process, container, volume, network, queue message, lock, lease, or
  persisted fixture state.
- `inconclusive`: arms are incomparable, noisy, censored, contaminated,
  missing, or have unstable reset evidence.
- `invalid`: any authority escape, fixture corruption, hidden-label exposure,
  failed reset, missing denominator, or replay mismatch.

Optimistic labels require comparable controls. Missing control evidence becomes
`inconclusive` or `invalid`, never `verified_helpful`.

## Metrics

P116 reports every metric with numerator, denominator, nullable value,
threshold, scenario family, fixture version, split, and seed set:

- environment reset success rate;
- initial-condition comparability rate;
- fault injection success rate;
- primary SLO improvement rate versus no-action;
- median and p90 recovery-time reduction versus no-action;
- natural-recovery miscredit rate;
- wrong-action non-credit rate;
- harmful intervention rate;
- rollback success rate;
- collateral damage rate;
- recurrence rate after recovery;
- replay consistency rate;
- repeated-seed variance by scenario family;
- orphan cleanup success rate;
- authority-boundary violation count.

Zero or missing denominators are `null` and `unevaluable`; they are never
coerced to success.

## Acceptance Gates

P116 can claim lab readiness only when one fresh release evidence set proves:

- successful reset = 1.0 across at least 500 experiments;
- comparable initial-condition fingerprints for every paired scoring cell;
- helpful actions improve primary SLO versus no-action in at least 80% of
  eligible cases;
- median recovery-time reduction at least 30%;
- natural-recovery miscredit count = 0;
- wrong-action credit count = 0;
- harmful intervention rate = 0 for any promotable allowlist;
- rollback success = 1.0 for all rollback-required actions;
- replay consistency >= 0.99 across independent reruns;
- every metric is reported per family and aggregate;
- all production authority counters are exactly zero.

## Release Evidence

The release bundle must bind hashes for:

- scenario registry and fixture manifests;
- action catalog subset used by the lab;
- baseline windows and contamination report;
- experiment plans and randomized execution order;
- raw observations and canonical outcome records;
- reset, rollback, orphan-cleanup, and replay receipts;
- metrics report with denominators;
- authority scan;
- verification profile output;
- independent review document.

Self-review, stale hashes, missing raw observations, aggregate-only metrics,
or an omitted natural-recovery control fail closed.

## Stop Conditions

Stop P116 and do not claim readiness if any lab path can reach production,
credentials, external clusters, cloud mutation, or live remediation authority;
if resets are not perfect; if controls are incomparable; if natural recovery is
credited as intervention success; if wrong actions are credited; if a harmful
case is hidden by aggregate metrics; or if independent replay cannot reproduce
the canonical outcome records.
