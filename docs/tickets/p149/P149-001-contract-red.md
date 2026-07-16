# P149-001 — Contract and RED tests

Status: DONE

- Freeze cohort, SLO, blast-radius, rollback, kill-switch, and report schemas.
- Add failing tests from `docs/operations/p149-test-spec.md`.
- Depends on: P148 final report.
- Write scope: `tests/test_p149_canary_control.py` and P149 fixtures.
- Acceptance/stop: exact five selectors collect, fail only for missing P149,
  and reject forged P148 evidence, cohort drift, or blast radius above one.
