# P69 Autonomous Worker Runner Roadmap

P69 consumes P68 dispatch packets and records worker claim/run/retry/state outcomes through a safe recording transport.

## Tickets

- P69-001: Consume packet-only dispatch output from P68.
- P69-002: Claim selected packets in deterministic ticket order.
- P69-003: Add recording worker transport that plans Codex execution without spawning processes.
- P69-004: Record worker run outcomes and planned commands.
- P69-005: Create retry queue entries for failed packet runs.
- P69-006: Persist resumable state with completed tickets, failed tickets, retry queue, and next runnable ticket.
- P69-007: Add CLI JSON/Markdown reporting for runner state.
- P69-008: Wire P69 into release evidence and verify profiles.

## Boundary

Recording transport only by default. P69 does not spawn processes, execute shell commands, read credentials, call networks, call live APIs, execute actions, or mutate production.
