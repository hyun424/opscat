# P152-001 — Contract and RED tests

Status: DONE

- Freeze predecessor, permission, kill-switch, review, verification, and final evidence schemas.
- Add failing tests from `docs/operations/p152-test-spec.md`.
- Depends on: P151 final report.
- Write scope: `tests/test_p152_operator_readiness.py` and P152 fixtures.
- Acceptance/stop: exact five selectors collect, fail only for missing P152,
  and reject any missing/forged predecessor or unknown permission mode.
