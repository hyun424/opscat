# P151 Tickets

1. [P151-001 contract and RED tests](P151-001-contract-red.md)
2. [P151-002 sealed quality qualification](P151-002-quality-qualification.md)
3. [P151-003 evidence and verification](P151-003-evidence-verification.md)

## Normative execution contract

- Write scope: `app/services/p151_ground_truth_quality.py`,
  `tests/test_p151_ground_truth_quality.py`, `scripts/run_p151_qualification.py`,
  `evals/p151/**`, this ticket directory, and the shared files explicitly
  assigned by `docs/operations/p147-p152-program-plan.md`.
- Acceptance selectors, artifact paths, validator names, release command, and
  fail-closed stop conditions are the exact P151 entries in that plan.
- Release scoring uses exactly 48 sealed offline rows; NVIDIA is descriptive
  non-release evidence only.
