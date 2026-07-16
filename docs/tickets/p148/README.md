# P148 Tickets

1. [P148-001 contract and RED tests](P148-001-contract-red.md)
2. [P148-002 judgment and reversible lab](P148-002-reversible-lab.md)
3. [P148-003 evidence and verification](P148-003-evidence-verification.md)

## Normative execution contract

- Write scope: `app/services/p148_reversible_lab.py`,
  `tests/test_p148_reversible_lab.py`, `scripts/run_p148_qualification.py`,
  `evals/p148/**`, this ticket directory, and the shared files explicitly
  assigned by `docs/operations/p147-p152-program-plan.md`.
- Acceptance selectors, artifact paths, validator names, release command, and
  fail-closed stop conditions are the exact P148 entries in that plan.
- NVIDIA and every external model are outside P148 execution; canonical
  `nvidia_call_count` is exactly zero.
