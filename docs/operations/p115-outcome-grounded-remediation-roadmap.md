# P115 outcome-grounded remediation benchmark roadmap

## Objective

Define the offline benchmark contract for selecting safe remediation actions
from P114 diagnosis evidence. P115 establishes schemas, partitions, scoring
rules, action-pack metadata, leakage controls, baselines, and release evidence.
It does not execute remediation, access credentials, authenticate users, mutate
systems, or grant action authority.

P115 scoring is provisional until P116 produces measured paired outcomes for
the same benchmark records. Textual action labels, runbook similarity, or
expert preference cannot satisfy the final P115 release gate without P116
outcome records.

## Boundary from P114

P114 ends at evidence-bound diagnosis selection. P115 may consume only sealed
P114 outputs:

- source lattice ID and version;
- selected `{service, fault}` hypothesis ID or abstention;
- cited evidence IDs and missing-evidence markers;
- candidate confidence/calibration fields;
- freeze and replay receipts;
- aggregate-only P114 release evidence.

P115 may not consume hidden scorer truth, prompt transcripts containing labels,
provider-private reasoning, action text emitted by a P114 adjudicator, or any
artifact created after a blind-label opening unless it is explicitly marked as
consumed development evidence.

## Scientific claim

P115 claims only that an action-selection benchmark is leakage-resistant,
auditable, and ready to be populated with measured outcomes. It does not claim
that OpsCat improves system health until P116 demonstrates paired
action/no-action/wrong-action effects in a controlled laboratory.

The final scorecard must therefore expose two states:

- `p115_contract_ready`: schemas, partitions, baselines, authority scan, and
  synthetic/dry evaluator fixtures pass.
- `p115_outcome_qualified`: P116 measured paired outcomes exist, are bound by
  hash, pass replay and attribution checks, and are imported into final scoring.

Only `p115_outcome_qualified` may be used for portfolio, release, or model-card
claims about remediation quality.

## Versioned contracts

Every artifact carries `schema_version` and rejects unknown major versions.

- `p115.diagnosis_action_boundary.v1`: immutable P114 source lattice reference,
  selected hypothesis or abstention, visible evidence IDs, missing-evidence
  markers, uncertainty, expected utility placeholder, required validation, and
  rollback binding. It contains no hidden truth and no executable command.
- `p115.incident_case.v1`: case ID, source family, system topology handle,
  time window, visible evidence handle, candidate diagnosis handle, eligible
  action-pack IDs, required evidence classes, partition group, and release role.
- `p115.action_pack.v1`: signed action catalog entry with action ID, family,
  prerequisites, contraindications, reversibility class, blast-radius estimate,
  expected effect, expected evidence, validation query, rollback plan, and
  executor-disabled metadata.
- `p115.outcome_contract.v1`: evaluator-owned hidden target binding for
  measured P116 outcomes, no-action arm, wrong-action arm, attribution window,
  harm predicates, recovery predicates, and natural-recovery controls.
- `p115.action_label.v1`: candidate-visible target space containing
  `act`, `no_action`, `investigate_more`, and `escalate` decisions with cited
  evidence, prerequisite checks, contraindication checks, expected benefit,
  expected harm, validation, rollback, and abstention reason.
- `p115.paired_score.v1`: final scorer output comparing selected action
  against measured no-action and wrong-action arms from P116. It includes exact
  numerators and denominators for each scenario family and partition.
- `p115.partition_manifest.v1`: grouped development/holdout split by source,
  service, incident family, topology, time, and action-pack family. Near
  duplicates and post-freeze edits fail closed.
- `p115.release_evidence.v1`: hash-bound manifest for schemas, action packs,
  scenario matrix, splits, baselines, evaluator, authority scan, P116 outcome
  imports, reports, and independent review.

## Scenario matrix

The benchmark must cover at least these 15 scenario families:

1. CPU saturation.
2. Memory pressure or leak.
3. Disk full or inode exhaustion.
4. Network delay.
5. Network loss.
6. Socket exhaustion or connection churn.
7. Bad deploy or configuration rollout.
8. Dependency timeout or outage.
9. Database pool exhaustion.
10. Queue backlog.
11. DNS failure.
12. Certificate expiry or trust failure.
13. Quota or rate-limit exhaustion.
14. Cache corruption, stampede, or stale data.
15. Traffic surge or skew.

Each family must include no-action and investigate-more cases. Each family must
also include at least one contraindicated action and one action that is
plausible from text but harmful or ineffective under measured outcomes.

## Scoring model

P115 scores decisions, not prose. A candidate receives input from the
candidate-visible envelope and emits one `p115.action_label.v1`.

Final scoring is blocked until the imported P116 record supplies measured
paired outcomes. The scorer then computes:

- optimal-action Top-1 and Top-3;
- outcome-weighted utility versus no-action and wrong-action arms;
- harmful-action selection rate;
- unnecessary-action selection rate;
- correct no-action rate;
- correct investigate-more rate when evidence is insufficient;
- correct escalation rate for permanently human-authorized operations;
- prerequisite compliance;
- contraindication avoidance;
- evidence citation validity;
- validation and rollback completeness;
- per-family and per-action-pack denominators.

No aggregate may hide a failing scenario family, action family, or release role.
Zero or missing denominators are `null`/`unevaluable`, never passing.

## Baselines

P115 requires two baselines before any optional LLM benchmark:

- deterministic rule baseline using diagnosis, evidence completeness,
  prerequisites, contraindications, reversibility, and blast-radius ordering;
- safe null baseline that chooses `investigate_more`, `no_action`, or
  `escalate` whenever outcome evidence or authority boundaries are incomplete.

An optional constrained LLM proposal benchmark may be added only after the
deterministic baseline, leakage checks, and authority scan pass. The LLM may
select only frozen action-pack IDs or first-class abstention/escalation labels.
It may not emit commands, credentials, shell text, Kubernetes or cloud mutation
requests, or unregistered actions.

## Authority boundary

P115 is offline and evaluator-only.

- Auth is deferred.
- Action authority is disabled.
- Production executions, credentials, shell/subprocess, Kubernetes, Ansible,
  cloud, database mutation, production adapters, network mutation, and online
  policy writes have exact-zero counters.
- `p115.action_pack.v1` may describe validation and rollback, but those fields
  are declarative benchmark metadata only.
- L3+ execution belongs to later roadmap phases and cannot be inferred from a
  P115 pass.

## Tickets

- P115-000 P114 diagnosis-to-action boundary contract.
- P115-001 incident/action/outcome ontology and immutable schemas.
- P115-002 signed action-pack catalog.
- P115-003 evaluator-owned hidden outcome contract and leakage controls.
- P115-004 no-action, investigate-more, and escalate labels.
- P115-005 counterfactual paired scoring.
- P115-006 scenario matrix and partition manifest.
- P115-007 deterministic and constrained proposal baselines.
- P115-008 frozen split, P116 outcome import, release evidence, and review.

## Acceptance gates

- scenario families >= 15 and cases >= 300;
- every scenario family has nonzero development and holdout denominators;
- every case has a sealed P114 boundary artifact or explicit diagnosis-abstain
  reason;
- every eligible action has prerequisites, contraindications, reversibility,
  blast radius, validation, rollback, and signer metadata;
- optimal-action Top-1 >= 0.70 after P116 outcome qualification;
- optimal-action Top-3 >= 0.90 after P116 outcome qualification;
- harmful-action selection <= 0.01 after P116 outcome qualification;
- correct abstention >= 0.90 when required evidence is absent;
- prerequisite and contraindication compliance = 1.0;
- evidence citation validity >= 0.98;
- every metric includes numerator, denominator, nullable value, and partition;
- P116 measured paired outcomes are present before final scoring or the release
  status is `p115_contract_ready` only;
- production executions, mutations, credentials, auth, and action authority = 0.

## Stop rules

- Do not finalize P115 scoring without P116 measured paired outcomes.
- Do not score from textual action labels, runbook similarity, or submitted
  success fields.
- Do not open hidden outcome bindings before the split, evaluator, baselines,
  and release gates are frozen.
- Do not tune on holdout or P116 outcome-qualified labels after first scoring.
- Do not allow an LLM to invent action IDs, validation queries, rollback plans,
  commands, credentials, or authority.
- Missing or unverifiable evidence always fails closed.
