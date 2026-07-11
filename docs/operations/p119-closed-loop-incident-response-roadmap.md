# P119 Closed-Loop Incident Response Roadmap / PRD

## Objective

P119 plans a local/mock/sandbox closed-loop incident response commander that
connects completed P115-P117 benchmark outputs and the P118 reactive execution
substrate documents into one replayable incident loop:

```text
detect -> diagnose -> evidence acquire -> select -> approve ->
local execute -> validate/rollback -> learn
```

P119 is documentation-only at this stage. It creates no runtime authority,
production access, source-code work, deployment permission, credential scope, or
live mutation path by itself.

## Source Context

- P115 defines signed action packs, action and non-action labels, validation
  metadata, rollback metadata, prerequisites, contraindications, outcome
  scoring, and exact-zero authority counters.
- P116 defines local paired controls for action, no-action, wrong-action,
  rollback, natural recovery, reset, replay, idempotency, crash recovery, and
  orphan cleanup.
- P117 selects only frozen P115 action-pack IDs or first-class abstention labels
  from sealed evidence. P117 has no execution authority.
- P118 documents the local/mock/sandbox execution boundary: operation envelopes,
  WAL, CAS, idempotency, leases, deterministic approval, validation, rollback,
  crash recovery, replay, frozen evaluation, L3 maximum, auth deferred, and
  exact-zero nonlocal authority counters.

## Product Claim

P119 may claim only "local/mock/sandbox closed-loop incident response planning"
until a future implementation passes frozen evaluation and independent
verification.

Even after future implementation, P119 may not claim production-safe autonomous
remediation, production readiness, operator replacement, live canary execution,
credentialed execution, live connector access, cross-system generalization, or
L4+ authority.

## Non-Authority Boundary

Every P119 artifact preserves these invariants:

- auth is deferred;
- users, sessions, RBAC, OIDC/SSO, production identity, credentials, secrets,
  and approval provenance are out of scope;
- maximum authority is L3 local/mock/sandbox;
- all targets are fixture-scoped and hash-bound to frozen manifests;
- production and staging mutation are forbidden;
- live connectors, external provider APIs, online policy writes, shell,
  subprocess, Kubernetes, cloud, database, and network mutation are unavailable;
- free-form action prose, LLM-generated commands, and invented action IDs are
  rejected;
- sandbox results cannot be promoted as production safety evidence.

Every release evidence bundle must report these counters, and all must be
exactly zero:

```text
auth_context_count
credential_scope_count
secret_material_count
shell_execution_count
subprocess_execution_count
kubernetes_mutation_count
cloud_mutation_count
database_mutation_count
network_mutation_count
live_connector_call_count
online_policy_write_count
staging_mutation_count
production_mutation_count
l4_plus_action_count
freeform_action_execution_count
llm_command_execution_count
authority_escape_count
```

## Incident State Machine

P119 models incidents as deterministic transitions guarded by WAL, CAS,
idempotency, leases, budgets, authority counters, and replay receipts.

Canonical states:

```text
detected
triage_started
diagnosing
evidence_acquiring
selection_pending
approval_pending
approved
local_execution_pending
local_executing
validating
rollback_pending
rolling_back
learning
recovered
escalated
aborted_fail_closed
expired
orphaned_recovered
```

Terminal states are `recovered`, `escalated`, `aborted_fail_closed`,
`expired`, and `orphaned_recovered`.

Core transition gates:

- `detected -> triage_started` requires deduplicated alert fingerprint and WAL
  open receipt.
- `triage_started -> diagnosing` requires sealed visible evidence or an
  explicit missing-evidence marker.
- `diagnosing -> evidence_acquiring` requires missing evidence or a P117-style
  `investigate_more` decision.
- `diagnosing -> selection_pending` requires a P114/P117-compatible diagnosis
  or diagnosis abstention.
- `evidence_acquiring -> diagnosing` requires fixture evidence receipt or
  budget-exhausted marker.
- `selection_pending -> approval_pending` requires a schema-valid P117 decision
  over frozen IDs or first-class non-action label.
- `approval_pending -> approved` requires deterministic P118-style approval and
  exact-zero authority counters.
- `approval_pending -> escalated` occurs for permanently human-authorized
  operations, policy rejection needing human judgment, or budget exhaustion.
- `approved -> local_execution_pending` requires a P118-compatible operation
  envelope and lease receipt.
- `local_execution_pending -> local_executing` requires CAS success and active
  owner lease.
- `local_executing -> validating` requires local action-attempt receipt or
  explicit action failure receipt.
- `validating -> recovered` requires measured postcheck evidence, no
  false-recovery marker, and satisfied attribution window.
- `validating -> rollback_pending` occurs on action failure, postcheck failure,
  ambiguous recovery, guardrail breach, collateral harm, or attribution
  uncertainty when rollback metadata exists.
- `rollback_pending -> rolling_back` requires owner lease and rollback WAL
  receipt.
- `rolling_back -> escalated` or `orphaned_recovered` requires rollback
  postcheck and orphan inventory.
- Any state may transition to `aborted_fail_closed` on authority drift,
  contract mismatch, WAL corruption, hidden production target, L4+ request,
  stale frozen hash, or replay mismatch.

Illegal transitions fail closed and append attempted-transition receipts.

## War-Room Timeline Contract

Every incident exposes an operator-grade local war-room read model derived from
WAL receipts. The timeline is append-only, redacted, hash-chained, and
replayable.

Required event classes:

- `incident_detected`
- `dedupe_or_correlation_decision`
- `triage_started`
- `evidence_packet_bound`
- `hypothesis_created`
- `hypothesis_falsified`
- `missing_evidence_identified`
- `evidence_acquisition_requested`
- `evidence_acquisition_completed`
- `decision_selected`
- `approval_requested`
- `approval_granted`
- `approval_rejected`
- `human_escalation_required`
- `operation_enqueued`
- `lease_acquired`
- `local_action_attempted`
- `validation_started`
- `validation_succeeded`
- `validation_failed`
- `rollback_started`
- `rollback_succeeded`
- `rollback_failed`
- `causal_attribution_recorded`
- `recurrence_checked`
- `learning_record_written`
- `incident_terminalized`
- `crash_recovery_resumed`
- `orphan_inventory_recorded`
- `authority_counter_snapshot`

Each event records incident state before and after, event type, timestamp,
actor type, source artifact refs, evidence IDs, decision episode ID when
present, operation ID when present, approval receipt when present, budget
snapshot, authority counter snapshot, previous hash, current hash, and
redaction receipt.

No timeline event may include credentials, secrets, production target strings,
shell text, subprocess commands, live connector payloads, or untrusted LLM
commands.

## Budgets and Escalation

Budgets are release gates, not best-effort hints. Exhaustion routes to
`investigate_more`, `escalated`, `expired`, or `aborted_fail_closed`; it never
forces an action.

Required budget dimensions include wall-clock incident budget, per-state
timeout, evidence-acquisition attempt count, value-of-information budget,
selector retry budget, approval wait budget, local operation lease duration,
operation retry count, validation window, rollback window, crash-recovery
resume budget, maximum incident WAL size, repeated-failure count per fixture,
and human escalation deadline.

Escalation is mandatory for selected `escalate` labels, permanently
human-authorized operations, exhausted evidence budgets, utility intervals that
cross zero, unresolved contraindications or contradictions, P118 approval
rejection, ambiguous validation, rollback failure, incomplete rollback evidence,
unproven crash ownership, recurrence after recovery, any authority-counter
drift, stale frozen hashes, tampering, or self-review.

Escalation payloads include incident ID, current state, severity, fixture,
selected label, selected action-pack ID when present, blocked reason, missing
evidence, contradictions, risk summary, budget snapshot, latest validation,
rollback status, authority counter snapshot, recommended human decision,
timeline refs, and replay bundle ref. Payloads remain local/mock metadata
because auth is deferred.

## Causal Outcome Attribution and Learning

P119 judges recovery by measured outcomes and matched controls, not plausible
text, action completion, or single-point postcheck success.

Allowed attribution labels:

- `action_helped`
- `no_action_recovered`
- `natural_recovery`
- `rollback_recovered`
- `action_harmed`
- `no_effect`
- `ambiguous`
- `invalid`

Credit rules:

- `action_helped` requires improvement over no-action and natural-recovery
  controls inside the attribution window with no guardrail breach.
- `no_action_recovered` and `natural_recovery` are never credited as action
  success.
- `rollback_recovered` is safety recovery, not action success.
- Missing controls, contaminated windows, stale telemetry, recurrence, or
  incomparable baselines produce `ambiguous` or `invalid`.
- Learning records are local/offline and cannot mutate online policy.

## Crash Recovery and Replay

P119 must recover from crashes before and after every state transition and
around all externalized local effects: detection, WAL open, diagnosis,
evidence acquisition request and receipt, selection, approval, operation
enqueue, lease acquisition, local action attempt, validation, rollback,
learning record write, terminal report write, and replay export.

Recovery reconstructs exactly one current incident state from WAL and CAS,
preserves idempotency for every side-effect boundary, prevents duplicate local
action attempts, inventories orphaned leases and partial work, and keeps
terminal replay read-only.

## Frozen Evaluation

P119 evaluation freezes before first score:

- incident fixture registry;
- alert and detection inputs;
- service topology handles;
- P114/P117-compatible evidence episodes;
- P115 signed action-pack manifests;
- P116 outcome references and control windows;
- P117 selector configuration and thresholds;
- P118 operation envelope and approval policy configuration;
- evidence-acquisition taxonomy;
- incident state machine;
- budgets and timeouts;
- escalation policy;
- validation and rollback probes;
- crash matrix;
- recurrence windows;
- learning policy and no-online-write constraints;
- authority scan rules;
- split assignments, seeds, and near-duplicate filters;
- release thresholds;
- independent verification inputs.

The first frozen score consumes the split. Failed unseen results become
recorded negative evidence, not tuning data. Stale hashes, post-score tuning,
self-review, hidden production targets, nonzero authority counters, missing
replay, aggregate-only metrics, or fail-open behavior block release.

## Ticket Sequence

1. P119-001 incident state machine and WAL contract.
2. P119-002 detect, correlate, and budgeted scheduler.
3. P119-003 diagnose and evidence acquisition loop.
4. P119-004 action selection and deterministic approval.
5. P119-005 local execution, validation, rollback, and false-recovery gate.
6. P119-006 war-room timeline, operator controls, and escalation.
7. P119-007 causal outcome attribution, recurrence, and learning.
8. P119-008 crash recovery, frozen evaluation, release evidence, and review.

## Acceptance Gates

P119 may advance beyond planning only when one fresh evidence set proves:

- every artifact preserves auth deferral and local/mock/sandbox-only execution;
- all action paths remain P115/P117 frozen-ID or first-class non-action labels;
- P118-style approval, validation, rollback, WAL, CAS, idempotency, leases,
  replay, and crash recovery are covered by adversarial tests;
- recovery claims require measured postcheck evidence and causal attribution;
- learning is local/offline and online policy writes remain exactly zero;
- all required authority counters remain exactly zero;
- frozen evaluation passes without retuning;
- independent verification is separate from planner and implementer.

## Stop Rules

Stop before implementation, evaluation, or release if any requirement would add
auth, credentials, secrets, production identity, staging or production
mutation, live connectors, online policy writes, shell/subprocess execution,
Kubernetes/cloud/database/network mutation, L4+ authority, free-form action
execution, LLM command execution, fail-open policy, hidden missing evidence,
false recovery, natural-recovery credit as action success, self-review, or
claims beyond local/mock/sandbox closed-loop incident response planning.
