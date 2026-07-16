# P148-002 — Judgment and reversible lab

Status: DONE

- Integrate deterministic safety-gated judgment only; external-model execution
  is outside P148.
- Implement process-owned lab capability, idempotency, postcondition, crash recovery, and rollback.
- Depends on: P148-001.
- Write scope: `app/services/p148_reversible_lab.py` plus the frozen shared
  contract API only.
- Acceptance: 10/10 cases, unresolved effects zero, canonical NVIDIA calls zero,
  exact-zero staging/production mutation, idempotent receipt and rollback.
- Stop: non-registry action, target ownership ambiguity, missing pre-state or
  rollback snapshot, or canonical external call.
