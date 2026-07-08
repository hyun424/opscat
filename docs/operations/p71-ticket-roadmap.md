# P71 Supervised Worker Execution Harness Roadmap

P71 adds a supervised execution harness after P70 command validation. It supports explicit process execution through an injected transport, captures artifacts, and persists state/retry outcomes.

## Tickets

- P71-001: Consume P70 process-capable commands.
- P71-002: Require explicit `--enable-process-execution` before starting runs.
- P71-003: Add simulated supervised transport for safe verification.
- P71-004: Add opt-in real subprocess transport interface for later supervised runs.
- P71-005: Capture stdout/stderr artifacts per ticket.
- P71-006: Persist completed, failed, blocked, and retry state.
- P71-007: Add CLI JSON/Markdown reporting for supervised execution results.
- P71-008: Wire P71 into release evidence and verify profiles.

## Boundary

Verification uses simulated supervised transport. Real subprocess execution is opt-in only and must remain behind explicit enablement, timeout, command gate, and artifact capture. No live APIs, credential reads, action execution, or production mutation are allowed.
