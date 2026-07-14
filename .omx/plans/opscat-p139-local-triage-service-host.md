# OpsCat P139 — Local Triage Service Host

## Decision

P139 turns the qualified P138 finite observation-to-triage supervisor into a
supervisor-friendly local service process. It proves process lifecycle,
exclusive whole-service ownership, restart reconciliation, deterministic local
health inspection, and hardened systemd/Compose contracts without granting any
new observation, credential, network, delivery, action, remediation, staging,
production, or operator-replacement authority.

P139 is the dependency-correct bridge between P138's in-process supervisor and
later dead-man notification or live observation work. External notification,
provider APIs, credentials, auth, and remediation remain deferred.

## P138 prerequisite correction

Before P139 qualification, the P138 production loop must bind each cycle's UTC
timestamp into the mutable P136 runtime `now` field and publisher-input
`created_at` field immediately before the cycle call. The current finite test
fixtures reuse their initial timestamp; a long-lived service would otherwise
evaluate receipt freshness and publication time against stale first-cycle data.
The change requires P138 regression tests, source-bound review/evidence
regeneration, `p138-release` reproduction, and P139 dependency constants bound
to the new P138 evidence/review hashes. Evaluator-provided `now_values` remain
the deterministic oracle; production uses P138's existing UTC clock source.

## Required outcome

The repository must expose an `opscat-triage-service` console entrypoint with
three explicit commands:

1. `validate --bundle PATH --base-dir PATH` validates a canonical local service
   bundle and all bound P138/P136/P137 evidence without state mutation.
2. `run --bundle PATH --base-dir PATH` holds a nonblocking whole-service lease,
   installs safe SIGINT/SIGTERM handling, runs the real P138 production loop,
   and commits a hash-chained service-exit receipt at a between-cycle boundary.
3. `status --bundle PATH --base-dir PATH` securely validates the service receipt,
   P138 readiness, heartbeat, termination, checkpoint, and ledger bindings and
   returns one deterministic local health classification.

No command may discover configuration from environment variables, contact a
socket, invoke a provider, deliver a notification, execute a shell command, or
mutate staging/production.

## Runtime contract

### Canonical service bundle

The tracked schema is `p139.local_triage_service_bundle.v1`. It contains:

- `service_id`, `config_version`, `created_at`, and `base_dir_ref_hash`;
- the exact P138 config, P136 runtime map, and publisher-input map;
- qualified P138 release status, evidence hash, and implementation-review hash;
- relative paths for the service lease, exit receipt, exit history directory,
  and local status snapshot;
- exact positive limits for bundle bytes, exit-history retention, startup
  readiness age, and service-run wall/cpu/memory budgets;
- the shared exact 15-key P138 zero-authority map;
- `bundle_hash` over every other field.

The bundle file must be a regular non-symlink file, bounded before and during
read, canonical compact UTF-8 JSON with exactly one trailing newline, and
descriptor-revalidated against replacement. Absolute paths, traversal,
overlapping runtime paths, secret-like text, URLs, callable values, missing or
extra authority keys, booleans, negative counters, and unknown fields fail
closed.

### Whole-service lease

`run` acquires a nonblocking advisory lease before reading mutable P138 state
and retains it until the exit receipt and status snapshot are durable. A second
service instance performs no P136, publisher, P137, P138, receipt, or status
write. The inner P138/P136/publisher/P137 leases remain authoritative and are
not weakened.

### Startup reconciliation

Before a new P138 loop starts, P139 securely validates:

- the current P138 ledger/checkpoint/phase tuple;
- the prior service exit receipt and history chain, if present;
- P138 readiness/heartbeat/termination records when present;
- current tracked P138 release evidence and final review hashes;
- P138's bound P136/P137 evidence and review hashes.

The production runtime must not depend on repository-local `evals/` paths.
P139 source contains source-bound expected P138 status/evidence/review and
transitive P136/P137 dependency hashes. The release runner proves those
constants equal the current tracked artifacts. An installed runtime validates
the bundle against those source-bound constants; only the release profile reads
tracked evidence files.

P138 treats stale prior readiness/heartbeat records as a safe-stop condition.
Therefore P139 owns an explicit restart-control rollover before invoking a new
loop. Under both the whole-service lease and the P138 supervisor lease, it must:

1. validate the previous readiness, heartbeat, termination, ledger, checkpoint,
   and prior P139 exit receipt as one bound tuple;
2. write and fsync a `p139.restart_control_intent.v1` containing their hashes;
3. copy the validated terminal control tuple into immutable P139 history;
4. remove only the exact descriptor-revalidated fixed readiness/heartbeat
   records; P138 termination records remain immutable and are never removed;
5. fsync the containing directories and replace the intent with a durable
   completion record before starting P138.

Crash recovery at every rollover split revalidates all bytes and either
completes the same rollover once or fails closed. An unclean restart may roll
over fresh or stale controls only when they bind the last valid P138 ledger and
no service lease is held; otherwise it is blocked. P139 may not rewrite a P138
ledger, checkpoint, phase, publisher, P136, or P137 record during rollover.

A missing prior exit receipt is classified as `unclean_restart`, not silently
treated as clean. P139 then delegates exactly-once recovery to P138 and proves
that no already accepted P136 sequence or P137 ledger atom is duplicated.
Tampered, forked, stale, partially committed, or dependency-drifted state fails
closed before a new observation.

### Exit receipt and status

Each terminal run writes `p139.service_exit_receipt.v1` with:

- monotonically increasing generation;
- prior receipt hash;
- service bundle hash;
- start classification (`clean_start`, `clean_restart`, `unclean_restart`);
- P138 loop stop reason, cycles completed, final ledger hash, checkpoint hash,
  readiness hash, heartbeat hash, and termination hash;
- exact runtime and evaluator activity maps kept separate;
- exact shared zero-authority map;
- resource usage and receipt hash.

The fixed current receipt and immutable history record are committed with an
intent -> history -> current sequence so crash recovery never forks history.
Retention removes only securely revalidated history older than the configured
limit and never removes the current receipt or its direct predecessor.

`status` emits `p139.local_triage_service_status.v1` and one of:

- `ready` — current readiness and heartbeat are fresh and ledger-bound;
- `stopped_clean` — a valid terminal receipt and P138 termination agree;
- `stopped_unclean` — no process lease exists and the last run lacks a valid
  terminal receipt;
- `stale` — readiness or heartbeat age exceeds its bound;
- `blocked` — lease contention, tamper, fork, dependency drift, or unreadable
  durable state.

Status inspection is read-only and uses a caller-supplied UTC timestamp; it may
not read environment or wall clock implicitly in the core service API.
It probes the service lease without truncating or unlinking it: a held lease is
required for `ready`, while a free lease plus fresh active readiness is
`stopped_unclean` rather than falsely healthy.

## CLI and deployment contract

- Add `opscat-triage-service = "app.p139_service_cli:main"`.
- CLI accepts explicit paths only and emits one canonical JSON result.
- Exit codes: 0 success/clean terminal, 2 invalid input or blocked state, 3
  active lease conflict, 4 stale/unclean health.
- `deploy/p139/opscat-triage-service.service` must use `PrivateNetwork=true`,
  `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=true`, explicit
  read/write paths, bounded restart policy, SIGTERM, and the explicit bundle.
- `deploy/p139/compose.triage-service.yaml` must use an immutable digest,
  `network_mode: none`, read-only root, non-root user, no-new-privileges,
  explicit read-only bundle and read/write state mounts, bounded restart policy,
  and no environment secrets.
- launchd remains unqualified because it cannot prove the same network and
  filesystem isolation contract.

## Exact 32-case release denominator

1. canonical bundle validation with zero writes;
2. valid genesis service run to exact max-cycle stop;
3. zero-promotion cycle with no publisher/P137 call;
4. promotion published and accepted exactly once;
5. clean restart advances receipt generation and prior hash;
6. clean terminal-control rollover prevents stale self-stop on restart;
7. rollover crash after intent/history/removal recovers the same tuple once;
8. unclean restart after P138 `cycle_started` recovers same cycle;
9. unclean restart after P136 outcome or publisher intent recovers once;
10. service lease contention performs zero inner calls/writes;
11. P138 lease contention commits no service-success receipt;
12. P136 lease contention preserves all prior durable heads;
13. publisher lease contention preserves sequence and current bundle;
14. P137 lease contention retains current handoff for restart;
15. stale readiness blocks before observation;
16. stale heartbeat blocks before observation;
17. tampered readiness/heartbeat is blocked;
18. tampered termination/exit receipt is blocked;
19. forked or gapped exit history is blocked;
20. bundle symlink/replacement/non-regular file is rejected;
21. noncanonical, invalid UTF-8, missing-newline, or oversized bundle is rejected;
22. absolute/traversal/overlapping paths are rejected;
23. unknown fields, callable values, URLs, environment/secret text are rejected;
24. P138 release status/evidence/review drift is rejected;
25. transitive P136/P137 dependency drift is rejected;
26. SIGINT and SIGTERM stop only between cycles with bound receipt;
27. status reports fresh `ready` without writes while preserving immutable P138
    termination history;
28. status distinguishes clean, unclean, stale, and blocked states;
29. systemd manifest passes exact hardening validation;
30. Compose manifest passes exact hardening validation;
31. real subprocess clean run, terminal rollover, restart, and status succeed;
32. real subprocess forced termination and restart recover without duplicate
    P136 sequence, P137 atom, or P138 ledger entry; all runtime authority remains
    exact zero and resource budgets pass.

The denominator is immutable. Grouped cases must expose each required subcase
and fail if any subcase is skipped.

Cases 2, 5, and 31 must additionally prove that distinct cycle timestamps reach
both P136 receipt validation and publisher creation; static first-cycle time is
a release-blocking regression.

## Release evidence

Tracked artifacts:

- `evals/p139/input/local-triage-service-profile.json`;
- `evals/p139/output/canonical-matrix.json`;
- `evals/p139/output/freeze-manifest.json`;
- `evals/p139/output/release-evidence.json`;
- `evals/p139/final-implementation-review.json`.

Preliminary mode executes all 32 cases and freezes exact case inputs, configs,
expected results, actual results, resource usage, runtime/evaluator counters,
authority counters, source hashes, fixture hash, profile hash, and the exact
qualified P138/P136/P137 evidence/review bindings. Final mode consumes the
frozen matrix and manifest without regeneration and requires an implementation
review independent from the implementing identity with zero P0/P1/P2 findings.

The final implementation review must explicitly inspect service/P138 dual-lease
ordering, restart-control rollover split commits, lease-probed status truth,
runtime independence from tracked `evals/`, and evaluator-vs-runtime process
and signal accounting.

Release status:

`p139_local_triage_service_host_qualified`

## Verification

Required checks:

- targeted P138/P139 unit and integration tests;
- real CLI subprocess clean, contention, forced-stop, and restart tests;
- Ruff and Mypy over all new/changed files;
- `bash scripts/verify.sh --profile p139-release`;
- `bash scripts/verify.sh --profile p138-release`;
- `bash scripts/verify.sh --profile docs`;
- `bash scripts/verify.sh --profile full`;
- `git diff --check` and changed-file secret/symlink scan.

## Explicit non-goals

- authentication, authorization, tenancy, or browser sessions;
- credential storage or environment-based configuration;
- live provider APIs, DNS, sockets, or network access;
- external notification delivery;
- action execution, remediation, staging/production mutation;
- multi-host consensus/failover;
- 24/7 availability, operator replacement, or unattended production claims.

## Follow-on dependency order

1. P140 may adapt P139 health/exit receipts into P133-compatible local dead-man
   events without delivery authority.
2. P141 may qualify a reviewed outbound notification-only authority with no
   action capability.
3. Live provider observation requires a separate OA3/OA4 authority review.
4. Remediation remains blocked until observation, notification, identity, and
   approval authority contracts are independently qualified.
