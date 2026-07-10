# OpsCat P104-P108 Proactive Prevention Plan

## 1. Outcome

Advance OpsCat from a bounded incident diagnostic agent into a proactive,
evidence-seeking prevention loop that can detect a likely incident before user
impact, gather missing evidence, select a reversible preventive intervention,
apply it only inside an isolated canary/simulation boundary, verify the causal
effect, and learn from the measured outcome.

The target is not "take action whenever a metric looks unusual." The target is:

> Predict a bounded failure mode, prove that the evidence is sufficient, choose
> the smallest reversible intervention, validate it on a canary, and expand,
> roll back, or escalate from measured results.

P104-P108 do **not** authorize unrestricted production mutation. The default
path remains deterministic, local/mock, network-free, and action-disabled.
Opt-in NVIDIA calls may advise read-only investigation or forecast reasoning,
but deterministic policy retains all execution authority.

## 2. Current Baseline and Gaps

- P24/P25 already represent trend windows, ETA, confidence, risk routes, and
  non-executing prevention plans in
  `app/services/proactive_risk_sentinel.py:52-235`. However, the forecast is a
  deterministic slope/threshold heuristic (`:124-159`), not a calibrated
  estimate of whether a specific failure will actually occur.
- P101 exposes a closed read-only diagnostic catalog
  (`app/services/tool_using_hypothesis_investigator.py:52-70`) and a bounded
  hypothesis loop (`:162-244`). Its synthetic diagnostic lab returns all useful
  evidence from one expected tool and no evidence from every other tool
  (`:247-268`), which is too simple for evidence sufficiency, contradiction,
  partial visibility, or information-gain evaluation.
- P103 lets the LLM replan after a negative diagnostic result while hiding
  action authority (`app/services/llm_diagnostic_episode.py:24-107`). It hands
  off after any positive evidence (`:48-50`) rather than proving that the
  evidence is sufficient for a particular action.
- P100 already provides a deterministic evidence-to-action boundary and blocks
  low telemetry or conflicting sources
  (`app/services/stateful_incident_investigator.py:67-101`). It remains the
  downstream action policy until a stronger policy is independently proven.
- Existing safety infrastructure already evaluates confidence, simulation,
  blast radius, reversibility, prior failed actions, and environment
  (`app/services/night_autopilot.py:66-100`, `:290-315`) and fails closed for
  production or ambiguity (`app/services/policy_engine.py:267-307`). P106-P107
  must compose these gates rather than create a second policy system.
- The existing action simulator records expected effect, touched resources,
  rollback path, precondition gaps, and residual risk
  (`app/services/action_simulator.py:21-53`). It is the base simulation contract
  for preventive interventions.

## 3. Principles

1. **Evidence before intervention:** anomaly detection starts an investigation;
   it does not itself authorize remediation.
2. **Outcome over plausibility:** success means measured incident prevention or
   reduced risk, not a convincing LLM explanation.
3. **Smallest reversible step:** prefer observation, throttling, isolation, or a
   one-target canary over broad restarts, rollbacks, or global configuration.
4. **Deterministic authority:** the model may propose hypotheses, evidence gaps,
   or plans; typed validation and policy decide whether anything can execute.
5. **Honest uncertainty:** missing telemetry, contradictions, distribution
   shift, and weak causal evidence must produce abstention or escalation.

## 4. Decision Drivers

1. Prevent false-positive remediation from causing a larger incident.
2. Measure whether an intervention actually prevented a predicted failure.
3. Reuse P24/P100-P103 and the existing policy/simulation boundary without
   duplicating safety logic.

## 5. Architecture Decision

### Selected: staged proactive control loop

```text
trend window
  -> forecast candidate
  -> evidence-gap investigation
  -> evidence sufficiency gate
  -> preventive action plan
  -> simulation
  -> isolated canary
  -> post-check + counterfactual estimate
  -> expand | rollback | observe | escalate
  -> outcome ledger + offline policy update
```

The loop separates five decisions because they need different evaluators:

- **P104:** Do we have enough and non-conflicting evidence?
- **P105:** What failure is likely, when, and with what calibrated probability?
- **P106:** Which intervention has positive expected value after intervention
  risk, blast radius, and reversibility are considered?
- **P107:** Did a limited application improve the leading indicators without
  collateral regression?
- **P108:** Did the intervention prevent the predicted incident, and should the
  policy become more or less confident next time?

### Rejected: one end-to-end LLM agent

It is fast to demonstrate but makes scorer leakage, policy bypass, causal
confusion, and unsafe retries difficult to detect. It also cannot isolate
whether failure came from diagnosis, forecast, planning, execution, or learning.

### Rejected: forecast-only alerting

It improves alert timing but remains an observability product, not an agentic
operator. It cannot seek missing evidence, perform bounded interventions, or
learn from outcomes.

## 6. Sequential Delivery Plan

Every phase follows the same gate:

1. ticket/contract and threat model;
2. test specification and RED evidence;
3. implementation;
4. targeted unit/integration/eval verification;
5. independent code and safety review;
6. full `fast`, `docs`, and coverage gates;
7. benchmark evidence and final summary;
8. only then unlock the next phase.

### P104 — Evidence Gap Investigator

**Goal:** When current evidence is insufficient, contradictory, stale, or
single-source, identify exactly what is missing and select the read-only tool
with the highest expected information value. Do not hand off to action merely
because one correlated anomaly was found.

**Primary artifacts**

- `app/services/evidence_gap_investigator.py`
- `scripts/run_evidence_gap_investigator.py`
- `tests/test_evidence_gap_investigator.py`
- `evals/evidence_gap/seed/scenarios.json`
- `docs/operations/p104-ticket-roadmap.md`
- `docs/operations/p104-plan-review.md`
- `docs/operations/p104-final-summary.md`

**Ticket sequence**

1. P104-000 shared decision envelope with `episode_id`, `decision_id`,
   `EvidenceRequirement`, `EvidenceState`, `SufficiencyDecision`, provenance,
   freshness, and trace IDs. P105-P108 must consume this envelope rather than
   invent phase-local evidence shapes.
2. P104-001 typed hypothesis/evidence requirement contract.
3. P104-002 supporting, contradicting, absent, stale, and unavailable evidence
   states.
4. P104-003 enhanced evidence lab with partial, distracting, and conflicting
   tool results; scorer truth remains private.
5. P104-004 evidence sufficiency score with critical-evidence hard gates.
6. P104-005 next-tool selection by deterministic information-value proxy.
7. P104-006 optional LLM evidence-gap proposal with strict schema validation.
8. P104-007 repeated query, call budget, wall-clock budget, and provider-failure
   fail-closed behavior.
9. P104-008 exact escalation payload listing missing/contradicting evidence and
   the next unavailable capability.
10. P104-009 benchmark against P103 and fixed-tool baselines from equal states.
11. P104-010 release integration and independent safety review.

**Required scenarios**

- supporting evidence split across metrics and logs;
- one positive source contradicted by traces or deploy metadata;
- no data because telemetry failed versus valid data showing no anomaly;
- stale evidence that must not satisfy the gate;
- misleading distractor evidence;
- critical evidence available only through a blocked/unavailable tool;
- repeated/duplicate evidence;
- prompt-injected log content;
- natural recovery while evidence is gathered.

**Acceptance criteria**

- 100% of action-ready decisions cite all critical evidence requirements.
- 100% of contradiction cases block action handoff until adjudicated or
  escalated.
- 0 repeated tool executions and 0 mutating diagnostic calls.
- 0 scorer-truth fields in provider context.
- False-remediation handoff rate is lower than P103 on partial/conflicting cases
  without reducing valid-case recovery by more than 2 percentage points.
- Every abstention reports an actionable, specific evidence gap.

**Stop condition:** P105 cannot start until the benchmark proves that "evidence
not found" and "evidence proves absence" are represented and scored differently.

### P105 — Calibrated Failure Forecast Engine

**Goal:** Convert trend windows plus P104-qualified evidence into a prediction
of a concrete failure mode, lead-time interval, probability, impact scope, and
abstention reason. Replace raw threshold confidence with calibrated forecasts.

**Primary artifacts**

- extend `app/services/proactive_risk_sentinel.py` through a versioned adapter,
  preserving the P24/P25 public payload;
- add `app/services/failure_forecast_engine.py`;
- add `scripts/run_failure_forecast_benchmark.py`;
- add `tests/test_failure_forecast_engine.py`;
- add time-ordered fixtures under `evals/proactive/forecast/`.

**Ticket sequence**

1. P105-000 forecast/action split. The calibrated forecast must not carry an
   executable prevention plan. Preserve the P24/P25 payload through a versioned
   compatibility adapter and mark its existing `prevention_plan` as
   `legacy_advisory` until P106 compiles a policy-valid plan.
2. P105-001 forecast schema: failure mode, probability, ETA interval, impact,
   evidence IDs, model/rule version, and abstention reason.
3. P105-002 leakage-resistant, time-ordered train/calibration/test fixture split.
4. P105-003 deterministic baseline using current P24 slope/threshold logic.
5. P105-004 multi-signal forecast using trend, seasonality, deploy/config change,
   saturation, and cross-service correlation features.
6. P105-005 probability calibration and uncertainty intervals.
7. P105-006 distribution-shift and missing-feature abstention.
8. P105-007 optional NVIDIA forecast rationale, never used as uncalibrated
   execution confidence.
9. P105-008 lead-time and false-alert benchmark by risk family and severity.
10. P105-009 shadow replay on source-native/real-derived datasets.
11. P105-010 release verification and model-card documentation.

**Acceptance criteria**

- Report precision, recall, PR-AUC, Brier score, expected calibration error,
  median useful lead time, false alerts per service-day, and abstention rate.
- No random window split that can place future points from one incident in the
  training set and earlier points in the test set.
- At least 80% of true-positive forecasts provide useful positive lead time on
  the curated benchmark; exact threshold is reported per family rather than
  hidden by a global average.
- Brier score and calibration error improve over the P24 baseline; no production
  action gate consumes raw LLM confidence.
- 100% of low-coverage or shifted cases either abstain or retain a conservative
  route.

**Stop condition:** P106 remains blocked until probabilities are calibrated on a
held-out time-ordered set, real-derived useful-lead-time transfer satisfies
`held_out_useful_lead_time_rate - real_derived_useful_lead_time_rate <= 0.10`
per supported family using `useful_true_positive_count / true_positive_count`
for each split, the real-derived rate remains `>= 0.80`, required numerators and
denominators are present, and the false-alert burden is explicit. Missing
numerators, denominators, split/source identity, or zero `true_positive_count`
make the row `unevaluable` and keep P106 locked. If this gate fails, stop at a
shadow forecasting product instead of building speculative intervention layers.

### P106 — Preventive Action Planner

**Goal:** For a qualified forecast, rank preventive interventions by expected
avoided loss minus action risk and operational cost, while producing explicit
preconditions, rollback, blast radius, canary scope, and post-checks.

**Primary artifacts**

- `app/services/preventive_action_planner.py`
- versioned preventive runbook catalog under `config/` or `evals/prevention/`;
- `scripts/run_preventive_action_benchmark.py`
- `tests/test_preventive_action_planner.py`

**Ticket sequence**

1. P106-000 action-registry crosswalk. Every proactive capability must compile
   deterministically to a registered `ActionRequest` plus `PolicyContext`;
   reject unknown mappings before scoring. Capability strings from P24 are not
   executable identities.
2. P106-001 typed intervention contract and closed capability registry.
3. P106-002 preventive runbook eligibility and environment constraints.
4. P106-003 expected-value score including incident probability, avoided impact,
   intervention harm, reversibility, cost, and confidence.
5. P106-004 compose existing `ActionSimulator`, `BlastRadiusService`, incident
   memory, and `PolicyEngine`; do not duplicate their gates.
6. P106-005 extract one typed `PreventiveSafetyGateResult` from existing policy
   inputs for confidence, ambiguity, blast radius, rollback, simulation, memory,
   and environment. P106 and P107 consume it; Night Autopilot and policy must not
   gain a third divergent gate.
7. P106-006 no-op/observe-only baseline and safe fallback.
8. P106-007 mandatory canary, rollback trigger, and post-check contract.
9. P106-008 build the pre-incident treatment/control lab before executor work,
   including cohort interference, natural recovery, telemetry loss, and rollback
   replay semantics.
10. P106-009 optional LLM plan proposal constrained to registered capabilities.
11. P106-010 adversarial planner benchmark and harmful-action taxonomy.
12. P106-011 approval profile integration without adding auth.
13. P106-012 release verification and safety review.

**Acceptance criteria**

- 100% of executable candidates include evidence links, preconditions,
  simulation result, bounded blast radius, rollback, canary scope, and post-check.
- 0 unregistered, shell, secret-reading, destructive, or irreversible actions.
- Negative expected-value cases select observe/escalate rather than intervention.
- Conflicting, low-confidence, production-global, unknown-blast-radius, or failed
  simulation cases never auto-run.
- On the benchmark, planner regret and harmful-action rate are reported against
  curated operator runbooks and no-action baselines.

**Stop condition:** P107 cannot start until all mutation-shaped plans are
simulation-only and the policy path proves fail-closed behavior.

### P107 — Canary Prevention Executor

**Goal:** Execute only a registered local/mock or isolated test-harness
intervention on a bounded cohort, monitor guardrails, and choose expand,
rollback, observe, or escalate from measured effects.

**Primary artifacts**

- `app/services/canary_prevention_executor.py`
- `app/services/prevention_verification_loop.py`
- `scripts/run_prevention_canary.py`
- `tests/test_canary_prevention_executor.py`
- isolated fault-lab extensions for treatment/control cohorts.

**Ticket sequence**

1. P107-000 immutable `PreventionEpisode` and `PreventiveActionAttempt` schemas.
   Reuse the existing `ActionExecutionAttempt.idempotency_key` persistence path
   where compatible; otherwise add an explicit compatibility adapter and prove
   duplicate-delivery replay before any executor exists.
2. P107-001 execution state machine and idempotency contract.
3. P107-002 treatment/control cohort allocation with stable fingerprints.
4. P107-003 preflight policy recheck immediately before execution.
5. P107-004 bounded local/mock action adapter; production adapters remain absent.
6. P107-005 continuous primary and guardrail metric observation.
7. P107-006 minimum evidence duration and effect threshold.
8. P107-007 automatic rollback on guardrail breach, non-improvement, uncertainty,
   or telemetry loss.
9. P107-008 retry storm, concurrent agent, duplicate command, and partial failure
   defenses.
10. P107-009 causal canary benchmark against no-action and broad-action arms.
11. P107-010 release verification and execution-boundary review.

**Acceptance criteria**

- 100% idempotency under duplicate delivery and process restart replay.
- 100% rollback/escalation on guardrail breach, telemetry loss, or failed
  post-check; no repeated intervention after rollback.
- 0 execution outside the declared cohort and capability registry.
- Treatment and control begin from equivalent state fingerprints.
- Report risk reduction, recovery/prevention rate, collateral regression,
  rollback success, time-to-decision, and action count.
- Expansion is disabled by default; benchmark success does not silently enable
  production rollout.

**Stop condition:** P108 cannot start until an intervention outcome can be
replayed deterministically from the audit log and independently verified.

### P108 — Prevention Outcome Learner

**Goal:** Learn from whether a forecast and intervention were actually useful,
without allowing online self-modification of safety policy or runbooks.

**Primary artifacts**

- `app/services/prevention_outcome_learner.py`
- append-only outcome schema/store;
- `scripts/run_prevention_learning_eval.py`
- `tests/test_prevention_outcome_learner.py`
- benchmark promotion integration.

**Ticket sequence**

1. P108-001 immutable episode ledger linking signals, evidence, forecast, plan,
   policy, canary, rollback, and final outcome.
2. P108-002 outcome labels: prevented, delayed, unaffected, naturally recovered,
   harmful, inconclusive, and censored.
3. P108-003 counterfactual estimator using control/no-action evidence.
4. P108-004 credit assignment across forecast, evidence search, action choice,
   and execution.
5. P108-005 false-positive and near-miss feedback.
6. P108-006 offline threshold/runbook recommendation generator.
7. P108-007 holdout replay and regression pack generation.
8. P108-008 benchmark promotion gate with safety-zero invariants.
9. P108-009 drift report and rollbackable policy versioning.
10. P108-010 final system benchmark, documentation, and independent review.

**Acceptance criteria**

- Online episodes cannot directly rewrite safety policy, prompts, or executable
  runbooks.
- Every learning recommendation is reproducible from immutable evidence and has
  a before/after holdout score.
- Harmful outcomes and false positives can only make the policy more
  conservative automatically; broader authority requires explicit review.
- Promotion requires no regression in hard safety counters and statistically
  supported improvement across multiple seeds/time splits.
- Report prevented-incident precision, unnecessary-intervention rate, net
  avoided impact, harmful-intervention rate, calibration drift, and per-family
  performance instead of one aggregate score.

**Stop condition:** the proactive loop is complete only when the system can
explain, replay, and score why it predicted, investigated, intervened, rolled
back/expanded, and changed its future recommendation.

## 7. Cross-Phase Benchmark Design

The evaluation matrix must include four arms from identical initial state:

1. no action;
2. current P24/P103 heuristic path;
3. curated operator runbook;
4. P104-P108 proactive agent.

Each scenario runs across multiple seeds and time perturbations. Required
families include resource saturation, connection-pool exhaustion, queue lag,
retry storm, cache stampede, memory leak, disk exhaustion, certificate expiry,
deploy regression, configuration drift, dependency degradation, regional
imbalance, telemetry failure, natural recovery, and adversarial/misleading
evidence.

The scorecard must keep these dimensions separate:

- detection/forecast: precision, recall, calibration, lead time, alert burden;
- investigation: evidence sufficiency, contradiction recall, tool cost, gap
  quality, unnecessary-query rate;
- planning: action value/regret, reversibility, blast radius, safety violations;
- execution: prevented/recovered, collateral regression, rollback, latency;
- learning: holdout improvement, drift, harmful recommendation regression;
- hard-zero safety: production mutation, unregistered action, secret exposure,
  scorer leakage, repeated execution, policy bypass.

## 8. Expanded Test Plan

### Unit

- Typed schema and boundary validation for every new decision object.
- Evidence-state transitions, sufficiency, contradictions, staleness, and
  unavailable evidence.
- Probability calibration, interval construction, abstention, and drift.
- Expected-value action ranking and all policy rejection branches.
- Canary state transitions, idempotency, rollback, and telemetry-loss handling.
- Outcome labels, causal attribution, immutable ledger, and promotion gates.

### Integration

- P104 to P100 action handoff only after sufficiency.
- P104/P105 composition with P24 trend windows and P103 provider adapters.
- P106 composition with policy, blast-radius, simulator, and incident memory.
- P107 treatment/control execution against the isolated fault lab.
- P108 replay from the complete P104-P107 audit trail.

### E2E

- A rising connection-pool wait trend is detected before exhaustion, evidence is
  completed, the forecast is calibrated, load shedding is simulated/canaried,
  wait time improves without error regression, and the outcome is recorded.
- A false anomaly gathers evidence, finds no corroboration, and exits with no
  intervention.
- Conflicting telemetry never executes; it either gathers adjudicating evidence
  or escalates with the exact gap.
- Canary harm triggers rollback and makes the subsequent policy more
  conservative without editing executable runbooks online.

### Observability and operational tests

- Every decision emits traceable IDs, evidence IDs, model/policy versions,
  budget usage, policy reasons, and state transitions.
- Metrics expose forecast calibration, evidence gaps, abstention, action routes,
  canary outcomes, rollbacks, and provider/tool latency.
- Reports redact secrets and prompt-injected content.
- Process restart and event replay produce the same final state.

### Verification commands per phase

```bash
uv run --no-sync --extra dev pytest -q <phase-targeted-tests>
uv run --no-sync --extra dev ruff check app tests scripts
uv run --no-sync --extra dev mypy app tests scripts
bash scripts/verify.sh --profile fast
bash scripts/verify.sh --profile docs
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/coverage_gate.py \
  --json-output /tmp/opscat-p10x-coverage.json
```

The changed/new modules should target at least 80% line coverage where the
repository tracer can measure it honestly; the repository-wide configured gate
must also pass. Coverage alone is not a quality claim: every hard safety branch
requires a behavioral test.

## 9. Pre-mortem

### Failure 1: High offline score, harmful real-world false positives

- **Cause:** synthetic windows encode obvious thresholds and do not represent
  seasonality, topology changes, missing telemetry, or benign spikes.
- **Mitigation:** time-ordered splits, real-derived source-native replay,
  abstention/drift tests, false alerts per service-day, and shadow-only rollout.

### Failure 2: The LLM sounds causal but follows leaked labels

- **Cause:** expected tools, future outcomes, runbook answers, or post-incident
  evidence enter the provider packet.
- **Mitigation:** scorer/public-context separation, packet allowlists, leakage
  assertions, temporal cutoffs, and equal-state fingerprints.

### Failure 3: Canary automation becomes a production mutation backdoor

- **Cause:** planner output bypasses capability validation or environment scope
  is inferred from model text.
- **Mitigation:** no production adapter in P107, closed typed registry,
  deterministic environment/policy lookup, preflight recheck, idempotency, and
  hard-zero execution counters.

## 10. Risks and Mitigations

- **Counterfactual uncertainty:** an incident may not occur naturally, so
  "prevented" is not directly observable. Use control cohorts, matched replay,
  censored/inconclusive labels, and avoid credit when evidence is weak.
- **Alert fatigue:** optimize false alerts per service-day and abstention quality,
  not recall alone.
- **Unsafe optimization:** P108 may learn to intervene more often to maximize
  recovery. Keep hard safety constraints outside the learned policy and require
  promotion review for broader authority.
- **Benchmark overfitting:** preserve hidden holdouts, version scenario packs,
  report per-family results, and add failures found in shadow operation only to
  the next benchmark version.
- **Cost/latency:** enforce separate tool, model-call, token, and wall-clock
  budgets; cache only evidence with explicit freshness semantics.
- **Existing code duplication:** reuse P24 structures, P100 policy handoff,
  P101 tools, P103 provider validation, `ActionSimulator`, `PolicyEngine`, and
  the existing promotion gate.

## 11. Milestones and Dependency Gates

| Phase | Capability unlocked | Depends on | Exit evidence |
|---|---|---|---|
| P104 | autonomous evidence completion | P101-P103 | contradiction/sufficiency benchmark |
| P105 | calibrated pre-failure prediction | P104, P24/P25 | time-ordered forecast scorecard |
| P106 | safe preventive plan selection | P104-P105 transfer gate | registry crosswalk + treatment/control lab + safety-zero report |
| P107 | isolated preventive intervention | P106 policy/lab gate | idempotent treatment/control canary evidence |
| P108 | offline outcome learning | P104-P107 | holdout promotion and drift report |

Do not parallelize phase implementation across these gates. Within a phase,
parallelize only disjoint lanes such as corpus construction, implementation,
and independent verification after the public contracts are frozen.

## 12. ADR

### Decision

Build a staged, evidence-gated proactive control loop in P104-P108 and keep the
model advisory while deterministic policy owns execution.

### Drivers

- prevent incidents before impact;
- avoid false-positive remediation;
- produce causal, replayable evidence of intervention value.

### Alternatives considered

- one end-to-end LLM agent;
- forecast-only alerting;
- direct production integration before a canary/control benchmark.

### Why chosen

The staged loop isolates failures, composes existing safety systems, supports
honest benchmark comparisons, and permits progressive authority only after
outcomes are proven.

### Consequences

- More schemas and evaluation work before visible production action.
- Stronger portfolio and product evidence because each claim is measurable.
- Production mutation remains intentionally out of scope through P108.
- P106-P108 are conditionally planned, not automatically unlocked: failure of
  P105's transfer/false-alert gate intentionally ends the intervention track.

### Follow-ups

- After P108, define a separate production-readiness phase for live read-only
  shadowing, adapter certification, SLOs, multi-tenant isolation, and external
  safety review.
- Auth remains deferred per product direction; no phase should accidentally add
  authentication scope.

## 13. Execution Staffing and Handoff

Available role types relevant to this plan: `architect`, `critic`, `planner`,
`executor`, `test-engineer`, `debugger`, `code-reviewer`, `verifier`, `explore`,
and `researcher`.

Recommended durable execution is **Team + Ultragoal**:

- leader/Ultragoal: owns phase gates, benchmark ledger, and stop conditions;
- one `executor` (medium): implementation owner for the current phase;
- one `test-engineer` (medium): corpus and adversarial evaluator lane;
- one `architect` (xhigh): contract/safety review before implementation;
- one `code-reviewer` or `verifier` (high): independent post-implementation
  evidence review.

Suggested launch shape for one phase at a time:

```text
$ultragoal docs/operations/p104-p108-proactive-prevention-master-plan.md
$team 4 "Implement only the currently unlocked OpsCat proactive-prevention phase; follow its RED-GREEN-review-verify gate and return benchmark evidence to the leader."
```

Team must prove targeted tests, safety invariants, benchmark validity, and full
verification before shutdown. Ultragoal records those artifacts and unlocks the
next phase. `$performance-goal` becomes appropriate during P105/P107 benchmark
optimization; `$autoresearch-goal` is not the default because the deliverable is
production code and evaluator evidence, not a standalone research report.

Ralph is only a fallback when a persistent single-owner sequential fix/verify
loop is explicitly desired; it is not the preferred multi-phase coordinator.

## 14. Review Changelog

- Added the P104 shared decision envelope required by every downstream phase.
- Split calibrated P105 forecasts from P24's legacy advisory prevention plan.
- Made successful time-ordered, real-derived forecast transfer a hard gate before
  P106; failure intentionally stops the project at shadow forecasting.
- Added a deterministic P106 crosswalk from proactive capabilities to the
  existing `ActionRequest`/`PolicyContext` registry.
- Required one shared preventive safety result instead of a third policy gate.
- Moved treatment/control lab semantics before executor construction.
- Added immutable prevention episode/action-attempt and idempotency persistence
  requirements before P107 execution.
- Independent architect verdict moved from conditional block to satisfied after
  these changes; independent critic verdict: **APPROVED** with no required
  changes before execution.
