# P18A — Realtime Source Reader Tickets

P18A adds source-native incremental ingestion before model judgment quality evaluation. Runtime reads original sources incrementally; JSON is produced only for triggered evidence snapshots and replay/evaluation artifacts.

| Ticket | Status | Purpose |
| --- | --- | --- |
| P18A-001 | TODO | FileTailReader with cursor |
| P18A-002 | TODO | Lightweight log parsers |
| P18A-003 | TODO | Metric window parser |
| P18A-004 | TODO | Rolling incident window |
| P18A-005 | TODO | Trigger detector |
| P18A-006 | TODO | Evidence snapshot builder |
| P18A-007 | TODO | Real LogHub/NAB replay |
| P18A-008 | TODO | Release evidence |

Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; no unattended production-operation claim.
