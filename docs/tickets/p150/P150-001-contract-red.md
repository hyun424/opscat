# P150-001 — Contract and RED tests

Status: DONE

- Freeze accelerated-clock, schedule, fault, resource, continuity, and report schemas.
- Add failing tests from `docs/operations/p150-test-spec.md`.
- Depends on: P149 final report.
- Write scope: `tests/test_p150_unattended_soak.py` and P150 fixtures.
- Acceptance/stop: exact five selectors collect, fail only for missing P150,
  and reject forged P149 evidence, real sleeps in the accelerated fast path, or
  injected/non-monotonic time in the qualifying wall-clock path.
