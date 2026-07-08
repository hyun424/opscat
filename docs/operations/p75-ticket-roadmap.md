# P75 Local Safe Subprocess Runner Roadmap

P75 consumes P74 dry-run-ready commands and runs them through a local safe subprocess runner. Repository verification uses simulated local transport and keeps actual subprocess spawning at zero.

## Tickets

- P75-001: Consume P74 dry-run-ready execution plans.
- P75-002: Require explicit local subprocess enablement.
- P75-003: Add simulated local subprocess transport for verification.
- P75-004: Add actual local subprocess transport behind an extra confirmation flag.
- P75-005: Write stdout/stderr artifacts per local run.
- P75-006: Persist completed, blocked, failed, and retry state.
- P75-007: Add CLI JSON/Markdown reporting for local safe runs.
- P75-008: Wire P75 into release evidence and verification profiles.

## Boundary

Repository verification uses simulated local subprocess transport. Actual local subprocess execution is opt-in only and requires explicit local enablement plus actual-spawn confirmation. No shell command execution, live APIs, credential reads, network calls, production mutation, action execution, or unattended production claim are allowed in normal verification.
