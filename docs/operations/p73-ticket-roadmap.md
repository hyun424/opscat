# P73 Long-Run Loop Controller Roadmap

P73 turns the P72 multi-cycle orchestrator into a bounded long-run controller suitable for hours-long autonomous development windows. It deliberately avoids raw infinite loops and records explicit stop guards.

## Tickets

- P73-001: Repeat P72 stateful orchestrator windows under one controller.
- P73-002: Add duration and max-window stop guards.
- P73-003: Track planned sleep without sleeping in repository verification.
- P73-004: Stop on retry queue and preserve retry artifacts.
- P73-005: Stop on missing process execution enablement.
- P73-006: Persist controller-level resume state after every window.
- P73-007: Add CLI JSON/Markdown reporting for long-run windows.
- P73-008: Wire P73 into release evidence and verification profiles.

## Boundary

Repository verification uses simulated supervised transport and virtual elapsed time. Real subprocess execution remains opt-in only and must stay behind P70/P71/P72 command gates. No raw infinite loop, actual sleep, live APIs, credential reads, action execution, or production mutation are allowed.
