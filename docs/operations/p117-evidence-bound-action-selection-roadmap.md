# P117 Evidence-Bound Action Selection Roadmap / PRD

## Objective

P117 plans the implementation-ready, evidence-bound action-selection agent that
consumes P114 hypothesis lattices, P115 signed action packs, and P116 measured
outcomes. It selects the next benchmark decision from frozen IDs, including
active evidence acquisition and abstention labels, but it never receives
execution authority.

The agent may recommend only:

- a frozen P115 action-pack ID;
- `investigate_more` with a typed evidence-acquisition request;
- `no_action` with measured outcome support;
- `escalate` for permanently human-authorized operations;
- `abstain` when evidence, calibration, contracts, or authority boundaries are
  insufficient.

LLM output is proposal-only. It has no authority to execute, mutate, authenticate,
open credentials, call production adapters, invent action IDs, or override
deterministic gates.

## Source Context

- P114 produces sealed evidence graphs, deterministic hypothesis lattices,
  selected hypothesis IDs or abstention, cited evidence IDs, confidence fields,
  freeze receipts, replay receipts, and exact-zero authority counters.
- P115 defines signed action packs, first-class abstention labels, leakage
  controls, deterministic baselines, and final scoring contracts.
- P116 supplies measured paired outcomes for action, no-action, wrong-action,
  rollback, and natural-recovery controls.
- P117 turns those artifacts into an action-selection policy and tournament, not
  an executor or production remediation system.

## Product Claim

P117 may claim only that OpsCat can choose or abstain from a frozen benchmark
decision using sealed diagnosis evidence, signed action metadata, measured
outcome utility, calibration, contradiction handling, and replayable evaluation.

P117 may not claim autonomous remediation, production readiness, operator
replacement, safe execution, or live canary authority. Later execution phases
must re-review every action boundary.

## Non-Authority Boundary

Every P117 artifact must preserve these invariants:

- no production mutation, staging mutation, credential scope, authentication,
  cloud account, Kubernetes context, database mutation, network mutation,
  shell/subprocess execution, online policy write, or production adapter call;
- no action text from P114, hidden scorer truth from P115, or unsealed P116
  outcome label is candidate-visible;
- LLM output is parsed as an untrusted proposal and is discarded unless it
  references frozen IDs, visible evidence IDs, and schema-valid abstention
  labels;
- deterministic policy gates own final eligibility, fallback, and release
  status;
- every evidence-acquisition request is declarative benchmark metadata, never a
  live connector call or retrieval authority grant.

## Agent Input Contract

Each decision episode is an immutable tuple:

```text
decision_episode_id
schema_version
p114_lattice_ref
p114_selected_hypothesis_or_abstention
visible_evidence_ids
missing_evidence_markers
p115_case_ref
p115_signed_action_pack_refs
p116_measured_outcome_refs
calibration_profile_ref
utility_profile_ref
evaluation_split
frozen_seed
authority_boundary_receipt
```

P117 rejects episodes missing any referenced freeze, hash, replay, signer,
split, or authority receipt.

## Decision Output Contract

The selector emits one schema-valid decision:

```text
decision_episode_id
selected_label
selected_action_pack_id?
ranked_action_pack_ids
requested_evidence_classes
cited_evidence_ids
contradiction_set_ids
expected_utility
utility_interval
calibrated_confidence
abstention_reason?
deterministic_fallback_reason?
llm_proposal_receipt?
authority_boundary_receipt
```

`selected_label` is one of `act`, `investigate_more`, `no_action`, `escalate`,
or `abstain`. `act` requires a frozen P115 action-pack ID and cannot contain
commands, credentials, target selectors, shell text, or mutation instructions.

## Active Evidence Acquisition

P117 models evidence acquisition as a value-of-information decision over
candidate-visible evidence classes. It may request evidence only from a frozen
taxonomy, for example:

- missing metric window;
- missing log class;
- missing topology or dependency edge;
- missing recent deploy/config marker;
- missing saturation, error, queue, DNS, certificate, or quota signal;
- missing validation evidence required by a signed action pack.

Evidence requests are benchmark labels, not connector actions. The selector
must choose `investigate_more` or `abstain` when the expected value of acting is
not positive after uncertainty, harm, and authority penalties.

## Contradiction Handling

P117 must preserve contradictions instead of smoothing them away. The selector
tracks contradiction sets for:

- P114 hypothesis conflict;
- evidence timestamp or source conflict;
- action prerequisite conflict;
- contraindication conflict;
- P116 measured outcome disagreement across seeds;
- natural-recovery ambiguity;
- calibration drift or low repeat agreement.

Contradictions can lower utility, trigger evidence acquisition, force
deterministic fallback, or require abstention. A contradiction cannot be hidden
by aggregate confidence.

## Utility, Calibration, and Abstention

P117 ranks decisions by calibrated expected utility:

```text
expected_utility =
  measured_benefit_vs_no_action
  - expected_harm
  - uncertainty_penalty
  - contradiction_penalty
  - missing_evidence_penalty
  - authority_penalty
```

All utility inputs must carry numerator, denominator, nullable value, interval,
scenario family, action family, split, and source artifact hash.

The selector must abstain or request evidence when:

- required evidence is absent;
- prerequisites are incomplete;
- any contraindication is present;
- calibrated confidence is below the acceptance threshold;
- utility interval crosses zero for an action;
- P116 outcomes are missing, incomparable, contaminated, or stale;
- deterministic and LLM tournament disagreement exceeds the allowed band;
- any authority counter is nonzero.

## Deterministic vs NVIDIA Tournament

P117 evaluates two bounded selectors:

1. deterministic utility selector using P114 evidence sufficiency, P115 action
   metadata, P116 measured outcomes, calibration, and abstention rules;
2. optional NVIDIA LLM proposal selector constrained to frozen action-pack IDs,
   frozen evidence IDs, and schema-valid abstention labels.

The deterministic selector is the release baseline and final fallback. NVIDIA
may improve ranking only when contract validity, evidence citation validity,
calibration, harmful-action rate, abstention quality, and per-family utility
all clear gates. LLM wins are advisory; deterministic gates remain authoritative.

## Frozen Unseen Evaluation

P117 must freeze development and unseen evaluation before any tournament score:

- episode registry;
- P114 lattice references;
- P115 action-pack manifest;
- P116 outcome import manifest;
- evidence-acquisition taxonomy;
- utility formula and thresholds;
- calibration method;
- deterministic selector configuration;
- NVIDIA prompt, model, decoding, parser, and fallback rules;
- split assignments and near-duplicate filters.

The first unseen score consumes the split. Failed unseen results cannot be
retuned into a pass.

## Ticket Sequence

1. P117-001 evidence-bound decision episode contract.
2. P117-002 active evidence-acquisition taxonomy and value-of-information gate.
3. P117-003 contradiction ledger and fallback semantics.
4. P117-004 utility, calibration, and abstention policy.
5. P117-005 deterministic selector baseline.
6. P117-006 constrained NVIDIA proposal benchmark.
7. P117-007 tournament scorer and frozen unseen evaluation.
8. P117-008 release evidence, independent review, and stop-rule gate.

## Acceptance Gates

P117 can claim action-selection readiness only when one fresh release evidence
set proves all gates below:

- episode contract validity = 1.0 across the frozen unseen denominator;
- P114 sealed lattice, freeze, and replay references present for every episode;
- P115 action packs signed and hash-bound for every eligible action;
- P116 measured paired outcome references present for final action-utility
  scoring, or release status is downgraded to `p117_contract_ready` only;
- decision JSON/schema validity >= 0.995 for every selector;
- unknown action ID count = 0;
- invented evidence ID count = 0;
- command, credential, shell, mutation, production target, or authority text
  count = 0;
- evidence citation validity >= 0.98 overall and per scenario family;
- prerequisite compliance = 1.0;
- contraindication avoidance = 1.0;
- harmful-action selection rate <= 0.005 overall and exactly 0 for any
  authority-sensitive family;
- unnecessary-action selection rate <= 0.02;
- correct `investigate_more` >= 0.90 when required evidence is absent;
- correct `no_action` >= 0.90 when measured no-action or natural recovery
  dominates;
- correct `escalate` = 1.0 for permanently human-authorized operations;
- abstention precision >= 0.90 and abstention recall >= 0.90 on abstain-required
  cases;
- expected utility uplift versus safe-null baseline > 0 overall and nonnegative
  for every scenario family;
- deterministic selector repeat agreement = 1.0;
- NVIDIA proposal repeat agreement >= 0.90 if NVIDIA is reported;
- NVIDIA proposal cannot regress harmful-action, authority, or per-family
  utility gates versus deterministic baseline;
- deterministic-vs-NVIDIA disagreement report includes every changed decision,
  cited evidence, utility delta, and fallback reason;
- calibration expected calibration error <= 0.05 overall and <= 0.08 per family;
- utility intervals and denominators reported for every action family and split;
- frozen unseen replay consistency >= 0.99;
- independent review is authored by a different agent/context than the planner
  or implementer;
- all auth, credential, executor, shell, subprocess, Kubernetes, cloud,
  database, production adapter, network mutation, online policy write, and
  production mutation counters are exactly zero.

## Release Evidence

The release bundle must bind hashes for:

- P117 episode registry and schema;
- P114 lattice manifest and replay receipts;
- P115 signed action-pack manifest;
- P116 measured outcome import manifest;
- evidence-acquisition taxonomy;
- contradiction ledger;
- utility and calibration configuration;
- deterministic selector output;
- NVIDIA proposal output, parser receipts, and fallback records when enabled;
- tournament report with numerator/denominator metrics;
- frozen unseen split manifest and near-duplicate report;
- authority scan;
- verification profile output;
- independent plan/release review.

Self-review, stale hashes, aggregate-only metrics, hidden-label exposure,
missing denominators, missing fallback receipts, or any authority counter
nonzero fail closed.

## Stop Rules

Stop P117 and do not claim readiness if any requirement pressures the selector
to execute actions, call live systems, authenticate, use credentials, create
unregistered action IDs, consume hidden outcome labels, tune on unseen results,
ignore contradictions, coerce missing denominators to success, or report NVIDIA
proposal quality without deterministic fallback evidence. Stop release if P116
outcomes are absent from final utility scoring, except for the explicitly
downgraded `p117_contract_ready` status.
