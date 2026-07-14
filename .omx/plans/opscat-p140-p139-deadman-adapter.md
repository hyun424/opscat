# P140 P139-to-P133 Local Dead-Man Adapter

## Objective

Qualify a credential-free, network-free local adapter that evaluates the
current P139 service state and feeds a closed watchdog result into the existing
P133 `DeadmanOutbox`. P140 must reuse the exact P133 event/cursor/ack protocol;
it must not create a second notification schema or gain delivery/action
authority.

Release status: `p140_p139_deadman_adapter_qualified`.

## Authority boundary

Runtime authority remains exact zero for credentials, network calls, connector
writes, arbitrary commands, shell/subprocess execution, notification delivery,
remediation, staging mutation, and production mutation. Evaluator-owned process
launches and signals are reported separately. P140 is local evidence
persistence only; P141 is the earliest phase that may review outbound
notification-only authority.

Release evidence carries both exact authority schemas without merging them:
the P133/P121 event-counter tuple and the P139/P138 15-key forbidden-authority
tuple. Every required key is present, is an integer rather than a boolean, and
is exactly zero.

## Closed configuration

`p140.p139_deadman_adapter_config.v1` contains exactly:

- `schema_version`;
- `adapter_id`;
- `allowed_artifact_roots`;
- `p139_bundle_path`;
- `p139_base_path`;
- `p133_config_path`;
- `adapter_lease_path`;
- `max_config_bytes`;
- `max_runtime_seconds`;
- `max_peak_memory_bytes`;
- `config_hash`.

Canonical JSON is UTF-8, sorted-key, compact JSON with finite values only.
`config_hash` is `stable_hash` of the exact config after removing only the
`config_hash` field.

Paths are resolved relative to the P140 config file, must stay inside explicit
allowed roots, reject symlink components, and must have a non-overlapping
topology. The P139 bundle and P133 config are regular single-link files. Their
validated hashes are rebound on every check. P133 `state_path` must equal the
P139 bundle path and P133 `runtime_ref` must equal `p139:<service_id>`.

Unknown fields, non-finite numbers, booleans-as-integers, URLs, environment
references, secret/credential text, commands, provider endpoints, notification,
action, or remediation fields are rejected before runtime state is touched.

## Runtime composition

1. Acquire the whole-adapter advisory lease.
2. Load and revalidate the exact P140 config, P139 bundle, and P133 config.
3. Construct `P139DeadmanWatchdog`, which calls
   `inspect_local_triage_service` at the P133-supplied UTC time.
4. Call the existing `DeadmanOutbox.check_once()` or bounded/forever `run()`.
5. Release the P133 lease before the P140 lease.

Lease order is therefore P140 adapter lease -> P133 outbox lease -> non-mutating
P139 service-lease probe. P140 never acquires the P139 runtime lease and never
starts P139.

## Exact health mapping

| P139 observation | P133 watchdog result |
| --- | --- |
| `ready` with live lease and fresh controls | `heartbeat_current`, healthy |
| `stale` | `heartbeat_stale`, unhealthy |
| `stopped_clean` with valid receipt/termination | `runtime_stopped`, unhealthy |
| `stopped_unclean` | `runtime_stopped`, unhealthy |
| absent P139 control/receipt state | `state_missing`, unhealthy |
| target-state validation/hash/chain/ledger failure | `state_invalid`, unhealthy |

Adapter/config/path/authority failures are not observations and abort before a
P133 event. Target-state failures are observations and may open a redacted
`state_invalid` P133 event. The `state_hash` is the hash of the stable P140
projection of validated P139 status through
`p140.p139_deadman_state.v1`: service ID, P139 bundle hash, health, reason,
service-lease-held flag, ledger/readiness/heartbeat/exit-receipt hashes, and
exact-zero P139 authority. The projection excludes volatile `observed_at` and
P139 `status_hash`, preventing a fresh observation timestamp from creating an
`updated` event on every check. Absence is detected only when P139 inspection returns
`stopped_unclean/no_terminal_receipt` and readiness, heartbeat, and receipt
hashes are all null. Invalid observations use a deterministic redacted state
hash over the closed failure category plus the P139 bundle hash and P133 config
hash; they never hash raw paths or exception text. Missing observations use
`null`. P140 does not add raw paths, PIDs, exception strings, or receipt
payloads to P133 events.

## CLI and deployment

Add `opscat-triage-deadman`:

- `validate --config <explicit-path>`;
- `check --config <explicit-path> [--now <UTC>]`;
- `run --config <explicit-path> (--max-cycles N | --forever)`.

SIGINT/SIGTERM only request a stop between checks. Machine-readable errors go
to stderr with exit code 2. Unhealthy checks remain successful executions and
return the P133 transition result. systemd and Compose examples use no network,
no environment secrets, non-root users, dropped capabilities, read-only roots,
and one explicit writable local data mount.

## Exact 32-case qualification denominator

1. canonical config validates with zero writes;
2. fresh ready/live lease deduplicates healthy state;
3. ready-looking controls without service lease are never healthy;
4. stale readiness opens `heartbeat_stale`;
5. stale heartbeat opens `heartbeat_stale`;
6. clean terminal receipt opens `runtime_stopped`;
7. unclean stop opens `runtime_stopped`;
8. missing state opens `state_missing`;
9. tampered exit receipt maps to `state_invalid` without optimistic health;
10. tampered termination maps to `state_invalid`;
11. forked/gapped receipt history maps to `state_invalid`;
12. ledger mismatch maps to `state_invalid`;
13. old-generation replay cannot duplicate an event;
14. stale replay is unhealthy;
15. future control timestamp is invalid;
16. clean restart generation transition updates exactly once;
17. restart-control recovery remains single-chain;
18. crash after event write reuses the exact event;
19. completed cursor write deduplicates retry;
20. conflicting same-sequence event fails closed;
21. repeated identical unhealthy state deduplicates before reminder;
22. reminder boundary emits exactly once;
23. unhealthy reason change emits one linked update;
24. healthy recovery emits one linked recovered event;
25. P139 service lease probe never mutates P139;
26. P133 lease conflict leaves no partial P140 state;
27. P140 lease conflict loses before target reads/writes;
28. acknowledgement does not resolve the active incident;
29. retention prunes only validated acknowledged events;
30. escape/symlink/hardlink/overlap/nonregular paths are rejected;
31. secret/URL/env/webhook/action/unknown fields are rejected;
32. real subprocess validate/check/run/signal/restart plus manifests preserve
    exact-zero runtime authority and bounded resources.

The denominator and selector catalog are immutable. Grouped cases disclose all
subcases. Runtime authority is asserted from production results, not inferred
from evaluator process success.

## Tickets

1. P140-001: closed config and secure loader;
2. P140-002: P139 watchdog mapping and provenance binding;
3. P140-003: adapter lease, check/run APIs, safe signals;
4. P140-004: CLI and hardened deployment examples;
5. P140-005: transition, tamper, crash, retention, and subprocess tests;
6. P140-006: exact 32-case runner and frozen release evidence;
7. P140-007: independent implementation review, docs, verification profile;
8. P140-008: full verification, hygiene, Lore commit, private-main push.

## Verification gates

- test-first targeted unit/integration/subprocess coverage;
- exact P133 event validation and P139 status validation;
- Ruff and Mypy over all changed files;
- `bash scripts/verify.sh --profile p140-release` reproducing P133 and P139;
- `bash scripts/verify.sh --profile docs`;
- `bash scripts/verify.sh --profile full`;
- changed-file secret/symlink scan, generated-artifact scan, and
  `git diff --check`;
- source-bound final mode that cannot rewrite its frozen matrix or manifest;
- independent review with zero P0/P1/P2 findings.

The source binding contains exactly these paths:

- `.omx/plans/opscat-p140-p139-deadman-adapter.md`;
- `app/p140_deadman_cli.py`;
- `app/services/p110_evaluation.py`;
- `app/services/p121_signals.py`;
- `app/services/p133_deadman_outbox.py`;
- `app/services/p139_local_triage_service.py`;
- `app/services/p140_p139_deadman_adapter.py`;
- `app/services/p140_runner.py`;
- `app/services/p140_release_evidence.py`;
- `deploy/p140/opscat-triage-deadman.service`;
- `deploy/p140/compose.triage-deadman.yaml`;
- `docs/operations/p140-p139-deadman-adapter-roadmap.md`;
- `docs/operations/p140-plan-review.md`;
- `docs/operations/p140-test-spec.md`;
- `evals/p140/input/p139-deadman-adapter-profile.json`;
- `pyproject.toml`;
- `scripts/run_p140_p139_deadman_adapter.py`;
- `scripts/verify.sh`;
- `tests/fixtures/p140/__init__.py`;
- `tests/fixtures/p140/builders.py`;
- `tests/test_p140_p139_deadman_adapter.py`;
- `tests/test_p140_deadman_cli.py`;
- `tests/test_p140_runner.py`;
- `tests/test_p140_release_evidence.py`.

Dependency binding requires the current qualified
`evals/p133/release-evidence.json` hash plus the current qualified P139 evidence
and final-review hashes. Any source or dependency drift blocks final mode.

## Explicit non-goals

- external delivery, paging, webhooks, email, Slack, or ticket creation;
- authentication, credentials, provider APIs, DNS, or sockets;
- action execution, approval automation, remediation, or mutation;
- multi-host consensus/failover, 24/7 availability, or operator replacement.
