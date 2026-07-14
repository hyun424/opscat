# P139 Test Specification

## Scope

Prove that a real local process can host the P138 supervisor, stop safely,
restart without duplicate observation/triage effects, and expose trustworthy
local health while preserving the exact shared zero-authority boundary.

## Test layers

### Unit

- exact bundle schema, canonical JSON framing, byte bounds, UTF-8, regular-file
  and replacement checks;
- path topology, secret/URL/callable/environment-text rejection;
- lease conflict, receipt hashing, history chaining, retention, and crash
  recovery at intent/history/current split commits;
- terminal-control rollover intent/history/removal/completion split commits and
  exact dual-lease ordering without P138 ledger/checkpoint/termination mutation;
- readiness/heartbeat/termination/ledger/status classification, including
  fail-closed rejection of controls later than the explicit observation time;
- exact exit-code mapping and signal-controller behavior;
- systemd and Compose hardening parsers.

### Integration

- real P138 production-loop invocation through the P139 service API;
- distinct per-cycle UTC propagation into P136 `now` and publisher `created_at`;
- clean restart and four unclean restart boundaries;
- restart after an old stopped readiness/heartbeat tuple without stale self-stop;
- inner P136/publisher/P137/P138 lease contention;
- transitive P136/P137/P138 release-evidence drift;
- fixed-path durable-state tampering and fork detection.

### Real subprocess

- invoke the installed module with explicit bundle/base paths;
- validate and run one bounded cycle;
- inspect status from a second process;
- prove status requires a held service lease before reporting `ready`;
- send SIGTERM during a bounded poll interval;
- restart from the same state and prove exactly one accepted sequence/atom;
- hold one service process and prove a second returns lease-conflict without
  state mutation.

Evaluator subprocess and signal activity must be reported separately from the
runtime authority map. Runtime `subprocess_launch_count` and `signal_count`
remain zero because process launch and signal injection are evaluator actions.

## Exact denominator

The release runner implements the immutable 32 cases listed in
`.omx/plans/opscat-p139-local-triage-service-host.md`. Every case contains:

- frozen input and effective config hashes;
- expected and actual terminal result;
- component-call boundary evidence;
- durable pre/post-state hashes;
- runtime, evaluator, and exact zero-authority counters;
- wall/cpu/peak-memory usage and fixed budgets;
- executed status and per-case evidence hash.

Totals other than `expected=32`, `passed=32`, `failed=0` block release.

## Required commands

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev pytest -q tests/test_p139_local_triage_service.py tests/test_p139_service_cli.py tests/test_p139_runner.py tests/test_p139_release_evidence.py
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev ruff check app/services/p139_local_triage_service.py app/services/p139_release_evidence.py app/services/p139_runner.py app/p139_service_cli.py scripts/run_p139_local_triage_service.py tests/test_p139_*.py tests/fixtures/p139
UV_CACHE_DIR=/tmp/opscat-uv-cache uv run --no-sync --extra dev mypy app/services/p139_local_triage_service.py app/services/p139_release_evidence.py app/services/p139_runner.py app/p139_service_cli.py scripts/run_p139_local_triage_service.py tests/test_p139_*.py
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p139-release
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p138-release
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile full
git diff --check
```

## Failure policy

Any skipped case, source drift, dependency drift, nonzero runtime authority,
receipt/history fork, stale/tampered health accepted as ready, unsafe manifest,
subprocess duplicate, resource overrun, unresolved P0/P1/P2 finding, or final-
mode input rewrite sets release status to `p139_blocked`.
