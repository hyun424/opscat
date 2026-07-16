# P149 Tickets

1. [P149-001 contract and RED tests](P149-001-contract-red.md)
2. [P149-002 canary outcome control](P149-002-canary-control.md)
3. [P149-003 evidence and verification](P149-003-evidence-verification.md)

## Normative execution contract

- Write scope: `app/services/p149_canary_control.py`,
  `tests/test_p149_canary_control.py`, `scripts/run_p149_qualification.py`,
  `evals/p149/**`, this ticket directory, and the shared files explicitly
  assigned by `docs/operations/p147-p152-program-plan.md`.
- Acceptance selectors, artifact paths, validator names, release command, and
  fail-closed stop conditions are the exact P149 entries in that plan.
- No action may affect more than one process-owned disposable-lab target.
