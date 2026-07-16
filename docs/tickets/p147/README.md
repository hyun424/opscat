# P147 Tickets

1. [P147-001 contract and RED tests](P147-001-contract-red.md)
2. [P147-002 durable offline provider shadow](P147-002-durable-shadow.md)
3. [P147-003 evidence and verification](P147-003-evidence-verification.md)

Dependency order is strict. Every ticket requires targeted tests and review.

## Normative execution contract

- Write scope: `app/services/p147_durable_shadow.py`,
  `tests/test_p147_durable_shadow.py`, `scripts/run_p147_qualification.py`,
  `evals/p147/**`, this ticket directory, and the shared files explicitly
  assigned by `docs/operations/p147-p152-program-plan.md`.
- Acceptance selectors: the exact five `test_*` names in the program plan.
- Artifacts: `evals/p147/output/report.json`, `freeze-manifest.json`,
  `final-implementation-review.json`, and `output/release-evidence.json`.
- Validators: `validate_p147_report`, `validate_p147_freeze_manifest`,
  `validate_p147_final_review`, and `validate_p147_release_evidence`.
- Stop on any skip/xfail, schema/hash/predecessor mismatch, nonzero review
  finding, authority counter, or `p147-release` failure.
