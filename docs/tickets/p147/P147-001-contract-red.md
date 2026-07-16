# P147-001 — Contract and RED tests

Status: DONE

- Freeze exact provider, state, counter, report, and predecessor schemas.
- Add failing tests from `docs/operations/p147-test-spec.md`.
- Prove failure is caused only by missing P147 implementation.
- Depends on: P146 final evidence.
- Write scope: `tests/test_p147_durable_shadow.py` and P147 contract fixtures.
- Acceptance: collect the exact five frozen selector names; before GREEN, at
  least one selector fails only because the owned P147 module is absent.
- Stop: collection mismatch, predecessor acceptance without exact hash/status,
  or any non-P147 failure.
