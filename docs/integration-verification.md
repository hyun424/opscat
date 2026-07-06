# OpsCat Integration Verification Report

Worker-5 inspected the docs/integration lane on 2026-07-06 UTC. The verification target was a temporary archive checkout of the latest integrated worker-4 head available at the time:

- Commit inspected: `9cee31c2fe67538b4ca9cc928bec604f368dc255`
- Verification checkout: `/tmp/opscat-worker5-verify`
- External credentials used: none
- Production systems touched: none

## Summary

The implementation shape matches the intended local mock MVP at a high level, but the current integrated head is **not yet end-to-end verified**. Static checks, tests, and the README demo fail due to app/test API drift introduced across concurrent lanes. Compile and Docker Compose config checks pass.

## Smoke-check evidence

| Check | Result | Evidence |
| --- | --- | --- |
| `ruff check app tests scripts` | FAIL | `app/models/action.py` has E402/I001 import ordering issues; `tests/conftest.py` has unused `Iterator` plus undefined `Generator`, `Base`, and `get_db`. |
| `mypy --cache-dir /tmp/opscat-worker5-mypy-cache app tests scripts` | FAIL | 27 errors across 7 files, including missing `execute_mock_action` / `verify_recovery`, stale `PolicyEvaluation.reasons`, stale policy test call shapes, and missing test fixture imports. |
| `python -m pytest -q -p no:cacheprovider` | FAIL | 29 passed, 3 failed, 7 errors. Import failure: `cannot import name 'execute_mock_action' from app.tools.mock_actions`; fixture failures from missing `Base`; stale policy tests pass strings where `ActionRequest` is expected. |
| `python scripts/demo.py` | FAIL | ImportError loading `app.main` because `app.services.incident_service` imports missing `execute_mock_action` and `verify_recovery`. |
| `python -m compileall -q app tests scripts` | PASS | Exit 0. |
| `docker compose config` | PASS | Config rendered successfully. |

## Primary blockers

1. **Mock action API drift**
   - `app/services/incident_service.py` and `app/services/night_autopilot.py` import `execute_mock_action` and `verify_recovery`.
   - The inspected `app/tools/mock_actions.py` exposes class-based execution helpers instead.
   - Impact: FastAPI app import fails, pytest route tests error, and `scripts/demo.py` cannot start.

2. **Policy API drift in tests and services**
   - Current `PolicyEngine.evaluate` expects an `ActionRequest`.
   - Some tests still call it with action-type strings and an older `PolicyContext(mode=...)` shape.
   - Some services/tests expect `PolicyEvaluation.reasons`, while the inspected policy object exposes a singular `reason` field.
   - Impact: mypy errors and policy tests fail.

3. **Test fixture import gaps**
   - `tests/conftest.py` references `Generator`, `Base`, and `get_db` without valid imports in the inspected head.
   - Impact: API and MVP-flow tests error during fixture setup.

4. **Lint import placement**
   - `app/models/action.py` appends SQLAlchemy imports after dataclass/domain definitions.
   - Impact: ruff E402/I001 failures.

## Recommended next integration fix order

1. Reconcile `app.tools.mock_actions` with incident/night-autopilot service imports, either by restoring wrapper functions or changing services to call the class-based executor consistently.
2. Normalize `PolicyEvaluation` and `PolicyContext` usage across app services and tests.
3. Repair `tests/conftest.py` imports and route dependency overrides.
4. Re-run the full command set from `README.md`.
5. Only after all checks pass, mark the README deterministic demo as verified for the integrated branch.

## Full-demo gap

A full alert-to-approval-to-execution-to-report demo could not be completed because the FastAPI app import fails before the demo client starts. No real Sentry, GitHub, Slack, production mutation, or arbitrary shell execution was attempted.
