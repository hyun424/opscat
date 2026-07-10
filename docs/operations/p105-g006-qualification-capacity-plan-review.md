# P105 G006 Qualification-Capacity Plan Review

Date: 2026-07-10

Verdict: **APPROVE**

An independent critic reviewed the qualification-capacity amendment, test spec,
current scorer, closed registry/verifier paths, and existing actual-runtime
harnesses. Two earlier revisions were rejected for arithmetic, resource,
coverage, lead-time, adapter, and deduplication ambiguity. The approved revision
closes those blockers without lowering a floor or expanding authority.

Approved findings:

- 720 samples create at most 719 adjacent five-second intervals, or 3,595
  seconds per service.
- 128 services per split yield 460,160 seconds (5.325926 service-days), and
  both splits yield 920,320 seconds (10.651852 service-days) per family, above
  the implemented unchanged 7.0-day per-family union gate.
- Database 45..50-minute, queue 35..40-minute, and deploy 25..30-minute
  precursors fit the unchanged family forecast intervals.
- Counting coverage comes only from receipt-verified raw monotonic adjacency
  and conservative canonical segments; fleet evidence cannot use legacy
  `created_at + tick_seconds` construction.
- Database, queue, and deploy resource maxima, incident groups, control cohorts,
  private failure timestamps, source-window bindings, and cleanup stops are
  concrete enough for RED tests and implementation.
- Separate `database_fleet`, `queue_fleet`, and `deploy_fleet` root schemas,
  adapters, CLI arguments, receipt roots, and cross-profile rejection prevent
  legacy evidence from receiving fleet credit.
- No auth, credential access, external production endpoint, production mutation,
  action planning, or action execution is introduced.

Implementation may proceed with P105-031 RED tests. P106 remains locked until
P105-034 independently verifies the full unchanged release gate.

