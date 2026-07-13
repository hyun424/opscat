# P133-001 Contract, Redaction, and Authority

Status: complete; independently reviewed and release-qualified.

Implement the exact configuration, normalized watchdog snapshot,
event/cursor/ack schemas, safe-root validation, redaction rules, and exact P121
integer-zero authority map. Tests must reject unknown/secret/provider/action
fields, unsafe paths, raw runtime IDs, arbitrary errors, and boolean counters.
Enumerate and test the exact P131 reason-to-seven-value normalization map. P133
uses watchdog liveness only; source readiness is excluded.
