# P72 Stateful All-Day Loop Orchestrator Roadmap

P72 converts the P71 supervised single-run harness into a resumable multi-cycle loop that can keep advancing safe-local work for long unattended development windows.

## Tickets

- P72-001: Run P71 supervised harness repeatedly across loop cycles.
- P72-002: Accumulate completed ticket state and compute resume handoff.
- P72-003: Stop immediately when retry queue entries appear.
- P72-004: Stop safely when process execution is not explicitly enabled.
- P72-005: Persist orchestrator state and cycle checkpoints after every cycle.
- P72-006: Preserve stdout/stderr artifact links from supervised child runs.
- P72-007: Add CLI JSON/Markdown reporting for the stateful loop.
- P72-008: Wire P72 into release evidence and verification profiles.

## Boundary

Repository verification uses simulated supervised transport. Real subprocess execution remains opt-in only and must stay behind P70/P71 command gates, explicit enablement, timeouts, artifact capture, and state checkpoints. No live APIs, credential reads, action execution, or production mutation are allowed.
