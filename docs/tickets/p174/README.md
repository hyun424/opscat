# P174 Tickets — GCP Disposable Provider-Adapter Lab

Dependency: canonical P173 shadow approval evidence. Scope: one new GCP project,
two disposable Compute Engine VMs, three typed adapters, live evidence, and P174-owned
verification. Existing projects and production targets are forbidden.

1. **P174-001 — Project and cost foundation.** Add Terraform for a dedicated
   project, billing attachment, APIs, budget alerts, labels, VPC, target and
   observer VMs, bounded disks/network, and verified teardown.
2. **P174-002 — Workload and observability lab.** Deploy API, worker, database,
   cache/queue, load generation, Prometheus, Loki, host evidence, health checks,
   resource limits, and private-only firewall rules.
3. **P174-003 — Identity and authority split.** Create attached target/observer
   VM identities, block container metadata access, and enforce action, fault,
   and evaluator boundaries with exact capabilities and negative authority tests.
4. **P174-004 — Real telemetry attachment.** Implement GCP Monitoring/Logging
   and Compute Engine read paths with bounded queries, redaction, immutable receipts,
   freshness, source diversity, and no persisted raw credentials/responses.
5. **P174-005 — Typed provider adapters.** Implement `tune_pool`,
   `restart_worker`, and `rollback_canary` with dry-run, preflight, execute,
   post-check, rollback, lease, idempotency, kill switch, and deadman.
6. **P174-006 — Sealed fault scenarios.** Implement ground-truth-separated load
   and fault schedules for reactive, precursor, healthy, ambiguous, duplicate,
   timeout, collateral, rollback, and authority-failure cases.
7. **P174-007 — Independent outcome evaluator.** Measure recovery, durability,
   collateral regressions, rollback closure, false action, abstention, timing,
   and target escape without using the agent's self-report as truth.
8. **P174-008 — Live apply and smoke.** Apply only a reviewed plan, verify
   project/VM/IAM/network boundaries, and prove real telemetry and one
   supervised action per adapter.
9. **P174-009 — Adversarial matrix and soak.** Run at least 100 action episodes,
   healthy windows, restart/resume, kill switch, deadman, and bounded elapsed
   soak while collecting cost and resource evidence.
10. **P174-010 — Freeze, review, and release.** Export artifacts, run independent
    review and full repository verification, bind predecessor/source/session
    hashes, state the maximum claim, and preserve a safe teardown path.
