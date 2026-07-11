# P116 Adversarial Test Specification

## Contract and Authority

- Reject experiment contracts missing schema version, immutable fixture ID,
  seed, action plan ID, observation windows, reset plan, rollback plan, or
  authority boundary declaration.
- Reject any contract that references production, staging, external Kubernetes
  contexts, cloud accounts, customer data, secrets, credentials, SSH, database
  credentials, broad network ranges, or non-disposable resources.
- Reject action plans with destructive, irreversible, secret-bearing,
  broad-blast-radius, unregistered, or unrollbackable operations.
- Verify all P116 results carry `execution_authority="lab_only"`,
  `production_authority=false`, `credential_scope=false`, and
  `p118_required_for_canary=true`.
- Static authority scan forbids production adapters and forbidden imports/calls
  in future runtime modules. Runtime evidence must report exact-zero counters
  for auth, credentials, external network, cloud, DB, production adapters,
  production mutation, and online policy writes.

## Fixture Reset and Fault Injection

- Prove fixture reset creates byte-stable canonical initial state for the same
  fixture version and seed.
- Detect leftover containers, processes, sockets, volumes, queues, locks,
  leases, files, ports, DNS entries, certificates, and persisted app state.
- Reject reset receipts that omit before/after hashes, fixture version, seed,
  cleanup inventory, or health window.
- Reject successful fault injection without a pre-fault healthy baseline and
  post-injection unhealthy evidence.
- Include adversarial cases for partial injection, double injection, stale
  injection receipts, injected faults that leak labels into candidate-visible
  state, and injection that survives reset.

## Baseline and Contamination

- Capture pre-fault SLO baselines for latency, errors, saturation, throughput,
  queue lag, dependency success, and fixture-specific guardrails.
- Reject contaminated baselines with unstable health, prior fault residue,
  duplicate experiment IDs, overlapping ports, reused volumes, clock drift,
  insufficient warmup, or missing coverage windows.
- Require public initial-condition fingerprints to exclude arm name, selected
  action, hidden oracle labels, and expected outcome.
- Reject paired arms with non-identical initial-condition fingerprints.

## Paired Outcomes

- For each eligible scenario, run action, no-action, wrong-action, rollback,
  and natural-recovery controls from comparable initial state.
- Randomize arm order and record the randomized schedule before execution.
- Repeated seeds must produce stable qualitative labels and bounded metric
  variance.
- Reject paired cells with missing raw observations, censored windows,
  incomparable controls, order-only effects, or hidden-label exposure.
- Natural recovery or no-op recovery cannot be credited as intervention
  success.
- Wrong-action recovery cannot be credited unless the wrong action is relabeled
  as correct through a predeclared scorer-owned action equivalence rule.

## Outcome Metrics

- Compute recovery time from first unhealthy observation to sustained healthy
  post-window.
- Compute primary SLO improvement versus matched no-action and
  natural-recovery controls, not versus an unmatched historical baseline.
- Compute collateral damage from guardrail regressions in services or metrics
  outside the intended action scope.
- Compute recurrence only after the declared recovery verification window.
- Publish numerator, denominator, nullable value, threshold, family, fixture
  version, split, and seed set for every metric.
- Missing or zero denominators are `null` and `unevaluable`, never passing.

## Crash, Idempotency, and Concurrency

- Kill the runner before action, during action, during rollback, during reset,
  and during report write; recovery must resume from the WAL without duplicate
  execution.
- Retry the same experiment ID concurrently; exactly one owner may execute a
  mutable lab step.
- Replaying completed experiments must not mutate the fixture.
- Orphan cleanup must handle stale containers, child processes, bound ports,
  mounted volumes, queued messages, leases, and partial reports.
- Crash recovery failures are release blockers even if outcome metrics look
  favorable.

## Replay and Freeze

- Freeze scenario registry, fixture manifests, action catalog subset, random
  seeds, split assignment, and scorer configuration before acceptance.
- Independent replay must recompute canonical outcome records from raw
  observations without trusting submitted labels.
- Reject replay drift in canonical metrics, labels, reset receipts, rollback
  receipts, authority counters, or experiment ordering.
- Development fixtures cannot be silently promoted to acceptance; overlap and
  near-duplicate detection are required.

## Named RED Cases

- `production_context_reference`, `credential_scope_present`,
  `external_cluster_context`, `secret_bearing_action`, and
  `unregistered_action`.
- `reset_leftover_container`, `reset_leftover_volume`,
  `reset_leftover_queue_message`, `reset_state_hash_drift`, and
  `fault_survives_reset`.
- `baseline_unhealthy`, `duplicate_experiment_id`, `overlapping_port`,
  `clock_drift_baseline`, and `short_warmup_baseline`.
- `arm_fingerprint_mismatch`, `arm_name_in_fingerprint`,
  `hidden_label_in_candidate_state`, and `expected_outcome_leak`.
- `natural_recovery_credited`, `wrong_action_credited`,
  `no_action_credited`, `missing_control_arm`, and `aggregate_masks_family`.
- `runner_crash_duplicate_action`, `rollback_crash_orphan`,
  `reset_crash_partial_state`, and `concurrent_owner_split_brain`.
- `replay_trusts_submitted_label`, `raw_observation_tamper`,
  `stale_release_hash`, `self_review`, and `missing_authority_scan`.

## Verification Profile

Future implementation must provide a targeted P116 profile that runs contract,
fixture, baseline, paired-runner, metrics, variance, crash recovery, replay,
natural-recovery, static authority, and release-evidence tests. Documentation
completion does not require those tests to exist yet.
