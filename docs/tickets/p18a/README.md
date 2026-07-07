# P18A — Realtime Source Reader Tickets

P18A adds source-native incremental ingestion before model judgment quality evaluation. Runtime reads original sources incrementally; JSON is produced only for triggered evidence snapshots and replay/evaluation artifacts.

| Ticket | Status | Purpose |
| --- | --- | --- |
| P18A-001 | DONE | FileTailReader with cursor |
| P18A-002 | DONE | Lightweight log parsers |
| P18A-003 | DONE | Metric window parser |
| P18A-004 | DONE | Rolling incident window |
| P18A-005 | DONE | Trigger detector |
| P18A-006 | DONE | Evidence snapshot builder |
| P18A-007 | DONE | Real LogHub/NAB replay |
| P18A-008 | DONE | Release evidence |

Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; no unattended production-operation claim.
