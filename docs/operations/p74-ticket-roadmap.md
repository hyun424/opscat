# P74 Real Subprocess Execution Dry-Run Gate Roadmap

P74 adds the final dry-run safety gate before any real worker subprocess may be spawned. It verifies P70 command validation, explicit real-subprocess enablement, clean worktree state, process budget, artifact paths, and state recording while keeping actual spawns at zero.

## Tickets

- P74-001: Consume P70 process-capable command validation results.
- P74-002: Require explicit real-subprocess enablement.
- P74-003: Add clean-git worktree guard through an injected status provider.
- P74-004: Enforce max process budget before any real run.
- P74-005: Preserve P70 command-gate blocks and reasons.
- P74-006: Write dry-run stdout/stderr artifact placeholders per ticket.
- P74-007: Persist dry-run state and operator handoff.
- P74-008: Wire P74 into release evidence and verification profiles.

## Boundary

P74 is dry-run only. Repository verification must not spawn real subprocesses, execute shell commands, read credentials, call networks, mutate production, execute actions, or claim unattended production operation.
