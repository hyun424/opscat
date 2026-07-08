# P70 Gated Worker Process Runner Roadmap

P70 validates P69 planned worker commands against strict process-execution gates before any real process runner can be enabled.

## Tickets

- P70-001: Consume P69 planned worker commands.
- P70-002: Validate allowed binary and subcommand as `codex exec` only.
- P70-003: Require safety flags including `--sandbox workspace-write`, `--color never`, and `--file`.
- P70-004: Enforce prompt path confinement under the dispatch directory.
- P70-005: Preserve no-spawn recording process transport by default.
- P70-006: Report blocked unsafe commands with explicit reasons.
- P70-007: Add CLI JSON/Markdown reporting for process gate results.
- P70-008: Wire P70 into release evidence and verify profiles.

## Boundary

No-spawn process gate by default. P70 validates readiness for real process execution but does not spawn processes, execute shell commands, read credentials, call networks, call live APIs, execute actions, or mutate production.
