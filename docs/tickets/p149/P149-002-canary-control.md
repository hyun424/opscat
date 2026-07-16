# P149-002 — Canary outcome control

Status: DONE

- Implement one-target lab canary, SLO decision, automatic rollback, and kill switch.
- Cover improvement, harm, uncertainty, timeout, replay, and rollback failure.
- Depends on: P149-001.
- Write scope: `app/services/p149_canary_control.py` plus frozen helpers only.
- Acceptance: 8/8 cases, max affected targets one, rollback success rate 1.0,
  no unresolved effect, and kill switch always fail-closed.
- Stop: harmful/uncertain observation commits, timeout without rollback, or
  rollback receipt mismatch.
