# P140 Test Specification

## Contract tests

- Accept only the exact `p140.p139_deadman_adapter_config.v1` schema.
- Rebind P139 bundle and P133 config hashes on every check.
- Require P133 `state_path` to identify the P139 bundle and `runtime_ref` to be
  `p139:<service_id>`.
- Reject unknown fields, secret/URL/env/command/action text, non-finite values,
  unsafe roots, traversal, overlap, symlinks, hardlinks, and nonregular files.

## Mapping tests

- `ready` maps to healthy `heartbeat_current` only with P139's live lease and
  fresh controls.
- A readiness or heartbeat timestamp later than the explicit check time maps
  to redacted `state_invalid`; it cannot recover an incident.
- stale maps to `heartbeat_stale`; clean/unclean stop maps to
  `runtime_stopped`; absent state maps to `state_missing`; validated target
  corruption maps to `state_invalid`.
- P133 events contain no raw P139 path, PID, exception, receipt body, secret,
  or extra field.

## Durability and concurrency tests

- Adapter lease precedes P133 work and rejects a second process before target
  reads or writes.
- P133 event-before-cursor split commit reuses the same event on retry.
- Conflicting same-sequence events, malformed cursor/history, and lease
  contention fail closed.
- Repeated state deduplicates, reminder emits once at the boundary, state
  changes update once, and recovery links once.
- Acknowledgement does not resolve active health; retention removes only valid
  acknowledged events.

## Process and release tests

- `validate`, `check`, bounded `run`, forever signal stop, and restart execute
  in real subprocesses with evaluator activity separated from runtime authority.
- systemd/Compose manifests enforce no network, non-root execution, dropped
  capabilities, read-only roots, and explicit writable state.
- The exact 32-case catalog cannot skip, reorder, forge hashes, or hide nonzero
  authority.
- Final release mode consumes frozen source-bound artifacts without rewriting
  them and reproduces qualified P133 and P139 dependencies.
