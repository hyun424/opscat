# P151-001 — Contract and RED tests

Status: DONE

- Freeze sealed-truth, metric, failure-class, provenance, and report schemas.
- Add failing tests from `docs/operations/p151-test-spec.md`.
- Depends on: P150 final report.
- Write scope: `tests/test_p151_ground_truth_quality.py` and sealed fixtures.
- Acceptance/stop: exact five selectors collect, cover exactly 48 rows, fail
  only for missing P151, and reject prediction/truth leakage or forged P150.
