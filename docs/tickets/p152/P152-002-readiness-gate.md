# P152-002 — Integrated readiness gate

Status: DONE

- Implement exact predecessor validation and closed permission modes.
- Bind kill switch, deadman, idempotency, blast radius, postcondition, and rollback closure.
- Treat `approve_once` only as a local signed-fixture receipt until auth exists;
  reject missing, self-issued, forged, expired, mismatched, and replayed receipts.
- Depends on: P152-001.
- Write scope: `app/services/p152_operator_readiness.py` plus frozen helpers.
- Acceptance: 6/6 predecessor bindings (P146-P151), 8/8 integration cases, kill switch,
  deadman, rollback closure true, and production replacement exactly false.
- Stop: production authority, unrestricted tool/shell/message route, permission
  escalation, missing rollback closure, or predecessor rewrite.
