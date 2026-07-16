# P152 Tickets

1. [P152-001 contract and RED tests](P152-001-contract-red.md)
2. [P152-002 integrated readiness gate](P152-002-readiness-gate.md)
3. [P152-003 final evidence and verification](P152-003-final-verification.md)

## Normative execution contract

- Write scope: `app/services/p152_operator_readiness.py`,
  `tests/test_p152_operator_readiness.py`, `scripts/run_p152_qualification.py`,
  `evals/p152/**`, this ticket directory, and the shared files explicitly
  assigned by `docs/operations/p147-p152-program-plan.md`.
- Acceptance selectors, artifact paths, validator names, release command, and
  fail-closed stop conditions are the exact P152 entries in that plan.
- Completion requires P122, secret scan, focused coverage, full verification,
  six qualified predecessor bindings (P146-P151), and
  `production_operator_replacement_ready=false`.
