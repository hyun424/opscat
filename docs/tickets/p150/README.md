# P150 Tickets

1. [P150-001 contract and RED tests](P150-001-contract-red.md)
2. [P150-002 accelerated chaos soak](P150-002-chaos-soak.md)
3. [P150-003 evidence and verification](P150-003-evidence-verification.md)

## Normative execution contract

- Write scope: `app/services/p150_unattended_soak.py`,
  `tests/test_p150_unattended_soak.py`, `scripts/run_p150_qualification.py`,
  `evals/p150/**`, this ticket directory, and the shared files explicitly
  assigned by `docs/operations/p147-p152-program-plan.md`.
- Acceptance selectors, artifact paths, validator names, release command, and
  fail-closed stop conditions are the exact P150 entries in that plan.
- The seven-day claim is accelerated deterministic time; no wall-clock seven-day
  or live-infrastructure claim is permitted.
