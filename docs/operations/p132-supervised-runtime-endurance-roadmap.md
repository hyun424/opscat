# P132 Supervised Runtime Endurance Qualification

## Outcome

Turn P131's foreground JSONL monitor into a process that can be safely managed
by an external supervisor and provide bounded, reproducible evidence for
graceful shutdown, crash recovery, split-brain prevention, resource limits,
and storage failure behavior.

P132 qualifies only the real local P131 process on one host. It does not claim
24/7 production availability, multi-host failover, direct live connectors,
external paging, authentication, credentials, remediation, or operator
replacement.

## Why P132 is distinct from P125

P125 exercises a deterministic shadow-replay durability model. P132 executes
the real P131 process, sends real process signals in a closed qualification
harness, verifies the real lease/checkpoint/report files, and validates
supervisor manifests. P125 evidence is not reused as P131 process evidence.

## Delivery slices

1. **Graceful lifecycle** - SIGTERM/SIGINT request a bounded clean stop, persist
   a termination receipt, release the lease, and make liveness fail immediately
   with `runtime_stopped` rather than waiting for heartbeat expiry.
2. **Storage envelope** - bound retained reports by count and total bytes,
   validate report ownership, and fail closed on low space or durable-write
   faults without claiming impossible inode guarantees.
3. **Supervisor contract** - structurally validate systemd, launchd, and Docker
   Compose examples with closed commands, restart throttling, graceful stop,
   non-root/container hardening, and no embedded secret or live connector.
4. **Process qualification harness** - use a closed module invocation in
   temporary local directories to prove graceful stop, crash/restart,
   second-instance rejection, process-independent watchdog behavior, and
   restart backoff/stable-window reset.
5. **Endurance and accounting** - run 1,000 deterministic cycles with 1,000
   generated local observations, zero lost/duplicated accepted rows, bounded
   retained reports, valid hashes, and exact resource denominators.
6. **Release evidence** - hash-bind runtime, process, supervisor, storage,
   resource, safety, source, and claim evidence into `p132-release`.

## Authority accounting

The monitor runtime keeps the exact P121 authority map and every value remains
integer zero, including `subprocess_execution_count`. The qualification harness
necessarily launches and signals local child processes. Those events are
reported separately as evaluator activity and never hidden inside runtime
authority. The harness permits no arbitrary command, network call, credential
read, connector write, remediation, staging mutation, or production mutation.

## Exact lifecycle contract

P132 extends monitor state with `lifecycle`:

- `phase`: `starting`, `running`, or `stopped`;
- `last_stop_reason`: `sigterm`, `sigint`, or null;
- `last_stop_requested_at`: RFC3339 UTC string or null;
- `last_stopped_at`: RFC3339 UTC string or null;
- `graceful_stop_count`: non-negative integer.

The signal handler may set only an in-memory event and reason. Normal control
flow finishes at an atomic cycle boundary, sets `phase=stopped`, writes state,
then writes a self-hashed `p132.termination_receipt.v1` containing runtime ID,
config hash, reason, request/stop timestamps, final cycle count, and final state
hash. `termination_receipt_path` must be inside an allowed artifact root.
Promotion requires exit within 3 seconds of the signal. The lease is released
only after state and receipt write attempts finish. Receipt failure exits
nonzero and remains unqualified.

`status` and `watchdog` both return unhealthy with `runtime_stopped` for a valid
stopped state. A killed process has no stopped transition and eventually
returns `heartbeat_stale`. Restart retains prior stop history, changes phase to
`running` only after lease ownership, and increments `resume_count`.

## Exact storage contract

P132 adds bounded positive config values `max_report_files`,
`max_report_dir_bytes`, and `min_artifact_free_bytes`. Retention may unlink only
a non-symlink regular file whose name exactly matches
`p131-health-YYYYMMDDTHHMMSSZ.json`, whose bounded JSON parses as
`p131.health_report.v1`, whose self-hash is valid, and whose `runtime_id` and
`config_hash` match the active runtime. Unreadable, tampered, foreign, or
unexpected candidates block cleanup rather than being deleted.

Failures before `os.replace` must leave the prior canonical file unchanged. A
directory `fsync` error after successful replace may leave a newer hash-valid
canonical file; P132 records durability as uncertain and requires a successful
reload plus subsequent durable rewrite before promotion. P132 never claims the
old inode survives a post-replace failure.

## Closed command contract

- The qualification harness may invoke only
  `[sys.executable, "-m", "app.monitor_cli", <run|watchdog|status>, ...]` with
  generated temporary local paths and fixed flags.
- Supervisor manifests use installed `opscat-monitor` and are accepted only
  when `pyproject.toml` maps it to `app.monitor_cli:main`.
- Shell wrappers, arbitrary arguments, provider endpoints, secrets, and action
  commands are forbidden in both forms.

## Required artifacts

- Service: `app/services/p132_supervised_runtime.py`
- Release evidence: `app/services/p132_release_evidence.py`
- Runtime changes: `app/services/p131_always_on_monitor.py`,
  `app/monitor_cli.py`
- Runner: `scripts/run_p132_supervised_runtime.py`
- Tests: `tests/test_p132_supervised_runtime.py`,
  `tests/test_p132_release_evidence.py`
- Manifests: `deploy/p132/opscat-monitor.service`,
  `deploy/p132/io.opscat.monitor.plist`,
  `deploy/p132/compose.monitor.yaml`
- Input: `evals/p132/input/endurance-profile.json`
- Outputs: `evals/p132/endurance-report.json`,
  `evals/p132/process-matrix.json`, `evals/p132/supervisor-ledger.jsonl`,
  `evals/p132/supervisor-validation.json`,
  `evals/p132/release-evidence.json`
- Verify profile: `bash scripts/verify.sh --profile p132-release`

## Promoted resource profile

`p132.endurance_profile.v1` fixes these local-only gates:

- 1,000 cycles and observations; injected 1-second cadence; 10-second reports;
- at most 8 reports and 1 MiB report-directory bytes;
- at least 1 MiB free artifact space and at most 1 MiB state bytes;
- at most 64 MiB traced peak memory, 30 CPU seconds, and 60 wall seconds;
- at most 3 seconds signal-to-exit and 2 MiB promoted temporary artifacts;
- at most 20,000 recent hashes, 10 records/64 KiB per cycle, 4 KiB per line;
- backoff `[1, 2, 4, 8, 16, 30]`, 30-second cap, 60-second stable reset.

These are qualification limits, not production SLOs.

## Promotion gates

- Expected and accepted observations are 1,000; lost and duplicate totals are
  exact integer zero.
- Report count, bytes, state, artifacts, memory, CPU, wall time, and shutdown
  latency meet the exact promoted profile.
- Graceful SIGTERM exits zero, persists a matching receipt, releases the lease,
  and reports `runtime_stopped`; SIGINT uses the same lifecycle path.
- Forced termination followed by restart resumes a valid checkpoint without
  accepting an old observation twice.
- A concurrent process exits nonzero with `runtime_lease_unavailable`; owner
  state remains valid.
- Restart delay is deterministic/capped/non-decreasing and resets after the
  stable window.
- Separate-process watchdog returns nonzero for stopped, stale, missing, and
  invalid state.
- Pre-replace storage faults preserve the prior checkpoint. Post-replace
  directory-sync faults produce only a hash-valid state plus explicit
  durability uncertainty and pass only after reload/rewrite recovery.
- Every supervisor manifest passes structural safety validation.
- Runtime P121 authority counters are exact integer zero. Evaluator process and
  signal counts are nonzero and separately disclosed; evaluator arbitrary
  command, credential, network, connector-write, and action counts are zero.
- Ruff, Mypy, P131 regression, targeted tests, release profile, and full project
  verification pass with current generated evidence.

## Stop conditions

- Clean stop can remain healthy, or crashed state is mislabeled cleanly stopped.
- Receipt does not bind final state, or signal handling performs I/O directly.
- Retention can delete unowned/tampered/symlinked files.
- Storage evidence claims the old inode survives post-replace sync failure.
- Two monitor processes can both own the lease.
- Manifests embed credentials, shells, unrestricted commands, live connectors,
  mutable images, privileged/host modes, or missing restart throttling.
- Evaluator activity is hidden or merged into runtime action authority.
- Any claim implies 24/7, production SLO, production autonomy, or operator
  replacement.
