# OpsCat P99 Final Summary — Comprehensive Operational Failure Matrix

P99 expands the P97 causal lab from 12 representative families and 120 cases to
52 families and 520 cases. The new catalog is vendor-neutral and spans resource,
storage, database, network, dependency, platform, messaging, scheduler,
configuration, security, data-integrity, regional, and cost failures.

## Implemented coverage

- Resource: memory leak, OOM kill, CPU throttling, thread-pool exhaustion, and file-descriptor exhaustion.
- Storage and database: disk capacity, disk IOPS, lock contention, replication lag,
  slow query, schema mismatch, data corruption, storage corruption, and search-index lag.
- Network and dependency: DNS, TLS expiry, packet loss, clock skew, rate limit,
  quota exhaustion, dependency brownout, stale discovery, and partial regional outage.
- Platform and traffic: autoscaling oscillation, traffic spike, cache stampede,
  retry storm, cascading failure, rollback failure, canary regression, and leader-election churn.
- Messaging and scheduled work: poison messages, duplicate processing, batch failure,
  missed jobs, and webhook delivery gaps.
- Configuration and governance: config drift, feature-flag drift, secret expiry,
  and cost runaway.

Each family has 10 comparable variants: obvious, noisy signal, ineffective first
action, partial recovery, peak load, missing telemetry, conflicting telemetry,
natural recovery, human-required, and compound failure.

## Full matrix measured result

Command:

```bash
./.venv/bin/python scripts/run_operational_scenario_matrix.py \
  --full-matrix --sample-size 10 \
  --output-json /tmp/opscat-p99-full.json \
  --output-md /tmp/opscat-p99-full.md
```

- Catalog: **52 families / 520 cases**
- Split: **312 development / 104 validation / 104 blind**
- Seeds: **3**
- Arms: **4,680** (`no_action`, `human_runbook`, and `opscat`)
- Actual loopback HTTP observations: **140,400**
- OpsCat recovery: **34.55%**
- Human-runbook recovery: **89.87%** after the P100 catalog-consistency correction
- No-action recovery: **11.47%**
- Causal recovery lift over no-action: **0.2308**
- Action-effectiveness precision: **80.64%**
- Escalation correctness / precision: **100% / 100%** across 720 expected escalation arms
- Harmful action rate: **0%**
- Unverified rate: **10%**
- Every hard safety counter: **0**

The lower recovery rate compared with P97 is useful evidence: broader and more
privileged cases expose the one-step selector's limits. The human baseline remains
far ahead, especially on multi-step, ineffective-first-action, and high-risk cases.

## Safety and claim boundary

- New actions are enumerated names that mutate only disposable in-memory lab state.
- No arbitrary shell, subprocess, filesystem mutation, credentials, external network,
  vendor API, product connector write, or production mutation is available.
- Human-required families expose a visible `privileged_scope_required` signal; the
  selector is not asked to infer an invisible permission boundary.
- The 520-case taxonomy is broad but not literally exhaustive. Organization-specific
  dependencies, architectures, and unknown failure modes still require extension.
- P99 does not prove production remediation effectiveness or operator replacement.

## Next handoff

P100 should add a stateful multi-step investigator that can request evidence,
re-rank hypotheses, try a bounded first mitigation, observe the outcome, and choose
a second action or escalation. P99 shows that expanding one-step mappings alone will
not close the gap to the human runbook.
