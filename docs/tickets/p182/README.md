# P182 Tickets - Limited Auto-Approval with Kill Switch and Auto-Demotion

## Goal

Permit a tightly bounded staging auto-approval lane for pre-registered,
reversible, low-blast-radius actions only after P181 real shadow mode passes.
The lane must include live kill switch, deadman, auto-demotion, rollback, and
human takeover.

## Non-Goals

- No production auto-approval.
- No auth, payment, billing, or tenant administration work.
- No new action families outside the reviewed allowlist.
- No concurrent multi-target automation.

## Dependencies

- P181 real shadow release evidence and operator acceptance.
- P179 self-monitoring, P180 statistical gates, and P174-P175 adapter evidence.

## Tickets

1. **P182-001 - Auto-approval policy profile.** Define exact eligible actions,
   targets, confidence, evidence, freshness, blast-radius, concurrency, and
   expiry requirements.
2. **P182-002 - Kill-switch authority.** Implement operator-owned global and
   target-local kill switches with receipt, propagation, and negative tests.
3. **P182-003 - Auto-demotion policy.** Demote to shadow/human-required on any
   monitor, evidence, metric, rollback, fatigue, provider, or policy anomaly.
4. **P182-004 - Limited executor lane.** Execute only reviewed reversible
   staging actions with lease, idempotency, post-check, rollback, and closure.
5. **P182-005 - Human takeover drill.** Exercise takeover before first action
   and during live run, including active lease cancellation and report handoff.
6. **P182-006 - Auto-approval campaign.** Run limited staged episodes with
   daily review, safety counters, demotion drills, and independent outcome
   scoring.
7. **P182-007 - Release evidence.** Bind policies, action receipts, rollback
   receipts, kill-switch drills, demotion receipts, and independent review.

## Concrete Deliverables

- `docs/tickets/p182/README.md`, `PRD.md`, and `test-spec.md`.
- P182-owned auto-approval policy profile, kill-switch authority, auto-demotion
  policy, limited executor lane, takeover drill, campaign runner, and release
  evidence bundle.
- Action, rollback, kill-switch, demotion, and human-takeover receipts.

## Architecture

P182 adds a separate limited auto-approval controller in front of the existing
typed action adapters. It must consume P177 evidence traces, P179 health state,
P180 statistical qualification, P181 shadow acceptance, and the P182 policy
profile. Any missing input demotes to shadow/human-required.

## Threat Model

- Bounded staging automation expands to production or unreviewed targets.
- Kill switch is stale, unreachable, or ignored.
- Auto-demotion fails while evidence or health is degraded.
- Rollback does not close an effect but the system continues.
- Human takeover lacks enough context to recover safely.

## Acceptance Metrics

- Complete at least 3 independent auto-approval campaigns on separate UTC dates,
  with at least 20 successful or safely closed auto-approved actions per campaign
  and at least 60 total across at least 2 reviewed action families and 2 staging
  targets. Only one action/target may be in flight at a time.
- Production mutation count = 0.
- Target escape, duplicate side effect, unsafe action, unresolved effect, failed
  rollback closure, failed human takeover, credential leak, failed kill-switch
  drill, and failed demotion counts = 0.
- Only one target and one action in flight unless a future PRD revises scope.
- Every auto-approved action has policy, evidence, health, lease, idempotency,
  post-check, rollback/human-takeover, and closure receipts.
- Required receipt completeness is 100% for every action and drill; a missing,
  malformed, unhashed, or unbound receipt is incomplete and blocks promotion.
  Required classes are policy decision, evidence snapshot, health snapshot,
  credential/target allowlist, lease, idempotency, dispatch, post-check, rollback
  plan, human-takeover readiness, final closure, and any triggered kill-switch,
  demotion, rollback, or takeover event. Non-triggered conditional events require
  a signed `not_triggered` receipt.
- Global and target-local kill-switch p100 latency is <= 5 seconds from signed
  activation receipt to dispatch block plus lease revocation. Active-operation
  cancellation or fail-closed isolation p100 is <= 10 seconds.
- Auto-demotion p100 latency is <= 30 seconds from first durable anomaly/monitor
  receipt to `shadow` or `human_required`, with zero action dispatch after that
  state transition.
- Each campaign runs at least 1 global and 1 target-local kill-switch drill, 1
  active-operation cancellation/isolation drill, 3 auto-demotion drills using
  distinct anomaly classes, 2 rollback drills, and 2 human-takeover drills. Thus
  the 3-campaign minimum requires at least 6 kill-switch, 3 active-operation, 9
  demotion, 6 rollback, and 6 takeover drills.

## Test Matrix

- Unit: policy eligibility, demotion reasons, kill-switch state, lease expiry,
  idempotency, rollback closure.
- Integration: typed adapters, P179 health, P177 evidence, P181 shadow ledger.
- E2E: limited auto-approval campaign with supervised staging target.
- Adversarial: stale evidence, monitor failure, kill-switch race, duplicate
  request, rollback failure, collateral regression, provider timeout, fatigue.
- Observability: action ledger, demotion ledger, human takeover report, daily
  operator review.

## Evidence Artifacts

`evals/p182/input/manifest.json`, `evals/p182/output/report.json`,
`evals/p182/output/freeze-manifest.json`,
`evals/p182/output/release-evidence.json`, and
`evals/p182/final-implementation-review.json`, plus
`evals/p182/output/campaign-manifest.json`,
`evals/p182/output/receipt-completeness-report.json`,
`evals/p182/output/safety-latency-report.json`, and
`evals/p182/output/rollback-takeover-report.json`.

## Rollback and Stop Conditions

Immediately demote or stop on kill switch activation, stale/missing evidence,
monitor failure, confidence drop, policy mismatch, duplicate action attempt,
collateral regression, unresolved effect, rollback failure, human takeover
failure, production reachability, or operator fatigue breach.

## Promotion Gate

No later authority phase may start unless all 3 campaigns, 60 actions, 100%
receipt completeness, p100 latency gates, and zero-failure counters pass with
reviewed operator acceptance and an explicit new PRD/test-spec. P182 does not
qualify production autonomy or general operator replacement. Its release evidence
must contain the exact phrase `not general operator replacement`.
