# P148-001 — Contract and RED tests

Status: DONE

- Freeze judgment, capability, action, rollback, receipt, and report schemas.
- Add failing tests from `docs/operations/p148-test-spec.md`.
- Depends on: P147 final report.
- Write scope: `tests/test_p148_reversible_lab.py` and P148 contract fixtures.
- Acceptance/stop: exact five selectors collect, fail only for missing P148,
  and reject forged P147 evidence or widened action authority.
