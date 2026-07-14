# P139 Local Triage Service Host Roadmap

P139 packages P138's qualified finite observation-to-triage loop as a hardened,
restartable local service process. It adds explicit config validation, a
whole-service lease, hash-chained exit receipts, deterministic status
inspection, safe signal handling, systemd/Compose contracts, and real
subprocess restart evidence.

The implementation contract is the approved plan at
`.omx/plans/opscat-p139-local-triage-service-host.md`. P139 remains local-only,
no-auth, credential-free, network-free, notification-free, and action-free.

## Tickets

1. P139-001: canonical service bundle and secure local reader;
2. P139-002: service lease, startup reconciliation, and exit-receipt journal;
3. P139-003: run/validate/status core APIs and CLI entrypoint;
4. P139-004: systemd and Compose hardening contracts;
5. P139-005: exact 32-case runner and real subprocess fixtures;
6. P139-006: frozen release evidence and independent implementation review;
7. P139-007: verification-profile, docs, and release integration;
8. P139-008: final regression, security scan, commit, and private-main push.

## Release boundary

P139 may claim `p139_local_triage_service_host_qualified` only after exact
32/32 evidence, zero runtime authority, source-bound independent review, final
mode no-regeneration, P138 dependency reproduction, docs/full verification,
and clean repository hygiene. This is not a production-autonomy or operator-
replacement claim.

## Implemented qualification surface

- `opscat-triage-service validate|run|status` accepts only explicit bundle and
  base paths; it performs no environment discovery and reads no credentials.
- The service lease is acquired before the P138 lease. Terminal readiness and
  heartbeat rollover is intent-journaled, archived, exact-byte checked, and
  recoverable at every split-commit boundary; immutable termination history is
  never removed.
- Exit receipts are bundle-bound, generation chained, crash recoverable, and
  retained with the current receipt and direct predecessor protected.
- `ready` requires fresh matching P138 readiness/heartbeat plus proof that the
  whole-service lease is held. A free lease with active-looking bytes is
  classified unclean rather than healthy.
- Production and evaluator process boundaries are separate. Evaluator
  subprocess and signal injection never appear in runtime authority counters.
- The systemd and Compose examples disable networking, drop capabilities, use
  read-only roots, non-root users, explicit writable state, and no secret
  environment.

The qualified boundary remains a local operational assistant host. P140 is the
next dependency: adapt local health and exit receipts into credential-free
dead-man events before any separately reviewed notification authority exists.
