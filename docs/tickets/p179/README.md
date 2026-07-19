# P179 Tickets - HA and Self-Monitoring

## Goal

Make OpsCat itself observable, highly available, restartable, and self-demoting.
P179 proves the runtime can monitor its own health, preserve ledgers across
failure, and fail closed when confidence in the monitor is lost.

## Non-Goals

- No new incident-action authority.
- No production mutation.
- No auth or payment scope.

## Dependencies

- P178 prevention ledger and P177/P176 evidence contracts.
- Existing heartbeat, deadman, restart, and release-evidence patterns.

## Tickets

1. **P179-001 - Runtime health model.** Define leader, worker, queue, evidence,
   clock, storage, model, provider, kill-switch, and deadman health signals.
2. **P179-002 - HA supervisor.** Implement active/passive or restartable
   supervisor behavior with monotonic generation IDs and duplicate suppression.
3. **P179-003 - Self-monitoring evidence.** Emit receipts for heartbeat, lag,
   resource use, evidence gaps, model/tool failures, and demotion decisions.
4. **P179-004 - Auto-demotion policy.** Fail closed to shadow/human-required on
   monitor failure, stale evidence, policy uncertainty, or resource breach.
5. **P179-005 - Chaos and restart drills.** Exercise process crash, clock skew,
   network outage, provider timeout, storage corruption, and kill-switch drills.
6. **P179-006 - Release evidence.** Bind HA run ledgers, chaos results,
   demotion receipts, and independent review.

## Concrete Deliverables

- `docs/tickets/p179/README.md`, `PRD.md`, and `test-spec.md`.
- P179-owned runtime health model, HA supervisor, self-monitoring ledger,
  auto-demotion policy, chaos drill harness, and release evidence bundle.
- Restart/resume, kill-switch, deadman, and monitor-failure drill reports.

## Architecture

Add a P179 runtime supervisor and self-monitoring ledger around the existing
observer/investigator/action-policy path. Do not alter action policies except to
demote on monitor uncertainty.

## Threat Model

- Silent monitor failure while OpsCat appears healthy.
- Duplicate actions or duplicate escalations after restart.
- Ledger gaps hide missed incidents.
- Failover preserves stale authority.

## Acceptance Metrics

- Restart/resume within 60 seconds with zero duplicate decisions.
- Heartbeat gap beyond two intervals triggers demotion.
- Kill switch and deadman drills pass 100%.
- Self-monitoring failure always demotes before any action-ready state.
- Production mutation and unsafe action counts = 0.

## Test Matrix

- Unit: health schema, generation IDs, duplicate suppression, demotion policy.
- Integration: restart/resume, ledger replay, queue/provider outage.
- E2E: 24-hour wall-clock HA shadow run with injected failures.
- Adversarial: clock skew, stale evidence, corrupted checkpoint, kill race.
- Observability: self-health report, demotion receipts, resource ceilings.

## Evidence Artifacts

`evals/p179/input/manifest.json`, `evals/p179/output/report.json`,
`evals/p179/output/freeze-manifest.json`,
`evals/p179/output/release-evidence.json`, and
`evals/p179/final-implementation-review.json`.

## Rollback and Stop Conditions

Stop on duplicate action/decision, unreported heartbeat gap, failed demotion,
ledger corruption without fail-closed status, kill-switch failure, or production
reachability.

## Promotion Gate

P180 may start only after P179 completes HA/self-monitoring evidence with
zero duplicate decisions and zero monitor-blind intervals.
