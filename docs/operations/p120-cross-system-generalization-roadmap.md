# P120 Cross-System Generalization Roadmap / PRD

## Objective

P120 plans a non-mutating cross-system benchmark generalization phase for
OpsCat. It evaluates whether the P117-P119 evidence-bound diagnosis,
action-selection, local execution, and closed-loop incident response stack keeps
useful quality, calibration, abstention, and fail-closed behavior when telemetry
shape, ontology, service topology, data source, and incident family change.

P120 is documentation-only at this stage. It creates no runtime authority,
production access, source-code work, test work, deployment permission,
credential scope, connector authority, or mutation path by itself.

## Product Claim

P120 may claim only cross-system benchmark generalization readiness after
frozen first-score evaluation, per-system analysis, and independent
verification.

P120 may not claim production-safe autonomous remediation, production readiness,
live connector operation, credentialed execution, operator replacement,
production mutation, or cross-system production safety.

## Source Context

- P117 selects frozen P115 action-pack IDs or non-action labels from sealed
  evidence. It is proposal-only and has no execution authority.
- P118 defines local/mock/sandbox execution over signed P115 packs selected by
  P117. It has L3 maximum authority, auth deferred, and exact-zero non-local
  authority counters.
- P119 connects detection, diagnosis, evidence acquisition, selection,
  approval, local execution, validation/rollback, attribution, war-room audit,
  crash recovery, frozen evaluation, and learning inside local/mock/sandbox
  authority only.
- P120 owns cross-system benchmark generalization. It does not convert P117,
  P118, or P119 evidence into production safety evidence.

## Non-Authority Boundary

Every P120 artifact preserves these invariants:

- auth is deferred;
- users, sessions, RBAC, OIDC/SSO, production identity, credentials, secrets,
  and production approval provenance are out of scope;
- P120 has exact-zero operational authority;
- read-only connector/importer conformance is not production permission;
- live production and staging connectors are forbidden;
- connector write paths, production/staging mutation, Kubernetes/cloud/
  database/network mutation, online policy writes, shell/subprocess execution,
  free-form action prose, LLM-generated commands, and L4+ execution are
  forbidden;
- local/mock/sandbox benchmark evidence cannot be promoted as production safety
  evidence.

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
```

## Generalization Protocol

P120 evaluates the full P117-P119 stack in three layers:

1. Data and ontology layer: source governance, import, normalization, ontology
   mapping, leakage/duplicate prevention, and split manifests.
2. Decision layer: diagnosis evidence binding, action selection, calibration,
   abstention, investigate-more, no-action, escalation, and baseline
   comparison.
3. Closed-loop layer: P119-style incident orchestration over local/mock/sandbox
   fixture systems, including validation/rollback evidence and causal outcome
   attribution, without production mutation.

The promoted evaluation denominator must include at least 3 distinct systems or
service architectures, 5 telemetry source classes, 20 incident scenario
families, both imported public datasets and local fixture/lab systems when
available, and at least one system absent from development, threshold
selection, prompt tuning, ontology-mapping tuning, and calibration fitting.

## Dataset and Source Governance

Every source must have a governance manifest covering source ID, source type,
license or usage basis, collection method, allowed use, privacy redaction
status, system ID, dataset origin, time range, telemetry modalities, topology
availability, labels, outcomes, actions, known biases, known duplicates,
near-duplicate fingerprint, split eligibility, holdout eligibility, authority
boundary receipt, and artifact hash.

Sources without license/usage basis, provenance, artifact hashes, authority
receipts, or clear lineage fail closed. Sources with credential material,
production target strings, unredacted secrets, mutation provenance, or unclear
authority fail closed. Public benchmark records, generated fixtures, local lab
outputs, read-only exports, and manually curated examples remain separately
typed. Missing labels, outcomes, and actions remain nullable and
denominator-visible.

## System-Level Splits and Holdouts

P120 splits by system identity first, not by row.

Required split axes are system ID, dataset/source origin, service architecture
class, topology graph family, telemetry source combination, incident scenario
family, action family, time window, generated-versus-observed lineage, and
ontology-mapping version.

No system can appear in both development and frozen unseen holdout. Calibration
fitting uses only development/calibration systems. Thresholds, abstention
policies, OOD cutoffs, prompts, parser rules, ontology mappings, connector
normalization rules, baseline configs, seeds, evaluator hashes, and release
thresholds freeze before first unseen-system score. The first score on a frozen
unseen system consumes that system split, whether it passes or fails.

## Near-Duplicate Prevention

Near-duplicate checks cover incident title and description text, normalized
telemetry windows, log template signatures, trace/span structure, topology
graph fingerprints, deploy/config marker sequences, root-cause labels, mapped
ontology paths, action-pack IDs, validation probes, rollback probes, outcome
windows, generated prompt lineage, and seed lineage.

The near-duplicate report includes numerator, denominator, threshold, method,
blocked pairs, manually adjudicated pairs, and unresolved pairs. Any unresolved
near duplicate touching a holdout system blocks release or removes that system
from the promoted denominator.

## Telemetry Normalization

P120 defines a canonical telemetry envelope covering telemetry record ID,
source ID, system ID, service ID, entity reference, modality, observed and
ingested timestamps, window bounds, signal name, value, unit, severity, labels,
topology refs, deploy/config refs, redaction receipt, normalization version,
source hash, and authority counter snapshot.

Normalization preserves raw source references and hashes, timestamp
uncertainty, clock skew, missing windows, delayed arrivals, duplicates, reorder
events, contradictory readings, nullable fields, modality identity, redaction
receipts, and authority receipts. Malformed, stale, delayed, duplicated,
reordered, contradictory, or unsupported telemetry routes to explicit
missing-evidence, contradiction, OOD, investigate-more, abstain, escalate, or
fail-closed outcomes. It must not be silently dropped from denominators.

## Ontology Mapping

P120 maps heterogeneous source labels into canonical OpsCat evidence classes,
entity/service/topology identities, incident families, root-cause and
hypothesis classes, action families and P115 action-pack references, outcome
and attribution labels, validation and rollback probes, and authority and
target classifications.

Mapping records include mapping ID, source label, source context, canonical
label, mapping confidence, ambiguity set, human-review requirement, evidence
refs, ontology version, split, system ID, and source hash. Ambiguous mappings
lower confidence, request evidence, abstain, or escalate. They must not be
coerced into confident action paths. Ontology mapping quality is a release
metric.

## Domain Shift and OOD Detection

P120 detects and reports telemetry modality missingness shift, signal
distribution shift, topology size/shape/dependency shift, incident-family
novelty, action-family novelty, ontology-mapping ambiguity, source-origin
shift, temporal drift, calibration drift, contradiction-rate shift, and
authority-boundary novelty.

OOD output includes system ID, dataset ID, shift dimensions, OOD score,
threshold, decision effect, recommended label, calibration effect, affected
denominators, and evidence refs. Allowed effects are
`continue_with_penalty`, `investigate_more`, `abstain`, `escalate`, and
`aborted_fail_closed`. OOD detection cannot trigger action execution.

## Calibration, Abstention, and Baselines

Calibration is fit only on eligible development/calibration systems and
reported on unseen systems with expected calibration error overall and per
system, confidence bins with denominators, abstention precision/recall,
investigate-more correctness, escalation correctness, no-action correctness,
utility intervals, and nullable metrics for every action family.

P120 compares OpsCat behavior against safe-null, P117 deterministic selector,
P117 NVIDIA proposal path if available, P119 alert-only/no-action loop,
retrieval or nearest-neighbor, and majority/prior baselines. All baselines use
identical denominators. Aggregate improvement cannot hide system-level
authority, harm, calibration, abstention, or degradation regressions.

## Metrics and Release Gates

P120 release evidence reports ingestion validity/loss by source and system,
normalization validity by modality, ontology mapping accuracy and ambiguity,
near-duplicate block rate, unresolved duplicate count, OOD effectiveness,
diagnosis/action/non-action/escalation correctness, harmful-action and
unnecessary-action rates, intervention-caused incident count inside
local/mock/sandbox allowlists, calibration ECE, abstention precision/recall,
investigate-more correctness, utility uplift, P119 closed-loop recovery metrics
where local fixture outcomes exist, false recovery declaration rate, replay
consistency, and exact authority counters.

Release requires at least 3 systems, 5 telemetry source classes, and 20
scenario families in the promoted denominator; connector/read-only ingestion
loss <= 0.1% under supported local load; unseen-system diagnosis/action quality
degradation <= 15 percentage points versus matched development-system
performance; harmful-action selection rate <= P117 gate and exactly 0 for
authority-sensitive families; escalation correctness = 1.0 for human-authorized,
auth-bearing, L4+, production-like, or mutation-like cases; read-only mode
unable to reach mutation surfaces; malformed or stale telemetry failing closed;
frozen replay consistency >= 0.99; and every exact authority counter equal to
zero.

## Phases

- Phase 0 - Documentation, test spec, plan review, and ticket handoff.
- Phase 1 - Source governance and dataset registry.
- Phase 2 - System-level split and near-duplicate guard.
- Phase 3 - Telemetry normalization and read-only connector contracts.
- Phase 4 - Ontology mapping and identity normalization.
- Phase 5 - Domain shift, OOD, calibration, and abstention.
- Phase 6 - Baseline harness and cross-system evaluation.
- Phase 7 - Frozen first-score release protocol.
- Phase 8 - Failure analysis, release evidence, and review.

## Tickets

1. `[planned] P120-001` - dataset source governance and import registry
2. `[planned] P120-002` - system-level split and near-duplicate prevention
3. `[planned] P120-003` - telemetry normalization and read-only connector contracts
4. `[planned] P120-004` - ontology mapping and identity normalization
5. `[planned] P120-005` - domain shift and OOD detection
6. `[planned] P120-006` - calibration, abstention, and baseline comparison
7. `[planned] P120-007` - frozen first-score evaluation and per-system metrics
8. `[planned] P120-008` - failure analysis, release evidence, docs, test spec, and review

## Stop Conditions

Stop before implementation, evaluation, release, or claim promotion if any
requirement would add auth, credentials, secrets, production identity,
credential scopes, live production/staging connectors, connector write paths,
production/staging mutation, Kubernetes/cloud/database/network mutation, online
policy writes, shell/subprocess incident action paths, L4+ authority,
free-form action prose, LLM-generated commands, retuning on frozen unseen
systems after first score, row-level splits, unresolved holdout duplicates,
hidden malformed telemetry, coerced ontology ambiguity, action on high-OOD or
low-calibration cases, aggregate-only metrics, omitted baselines, omitted
per-system failure analysis, nonzero authority counters, or claims beyond
cross-system benchmark generalization readiness.
