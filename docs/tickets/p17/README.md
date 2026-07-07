# P17 — LLM Policy Calibration Tickets

P17 adds deterministic approval calibration after LLM judgment. The goal is to prove OpsCat can use an LLM as an incident reasoning component without letting the LLM become the final execution authority.

| Ticket | Status | Purpose |
| --- | --- | --- |
| P17-001 | DONE | Calibration result schema |
| P17-002 | DONE | Context risk classification |
| P17-003 | DONE | Conservative route downgrade policy |
| P17-004 | DONE | Action filter |
| P17-005 | DONE | Provider evaluation integration |
| P17-006 | DONE | Report and verification integration |
| P17-007 | DONE | Release evidence |

Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; no unattended production-operation claim.
