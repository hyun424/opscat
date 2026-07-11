# P110-010 — Adversarial provenance hardening and local re-verification

## Why

The first independent implementation review rejected P110 even though its
targeted tests passed. Caller-supplied truth, batch reports, replay responses,
and release-review JSON could be forged without proving their relationship to
the pinned RCAEval archive and the actual provider run.

## Acceptance criteria

- Evaluation accepts only importer-shaped, pinned RE1-OB scorer truth and
  binds its stable hash into the report.
- The evaluator independently classifies action risk and fails closed on
  duplicate, missing, or unknown primary outputs.
- Replay is addressed by the full model/prompt/packet/decoding cache key.
- Batch merge verifies model, decoding, packet/cache, response, source,
  offset, and case-set provenance before recomputing metrics.
- Local release evidence requires the pinned official source, sealed truth,
  current implementation and candidate/evaluation file bindings, meaningful
  quality floors, zero safety violations, and a fresh independent review;
  hard qualification remains closed without cryptographic identity.
- Top-level documentation labels measurements unqualified until every gate
  and an independent re-review pass.
- Targeted P110 tests, Ruff, mypy, the P110 release profile, and the full fast
  profile pass with fresh evidence.

## Authority boundary

This ticket adds no remediation execution authority. NVIDIA output remains
diagnostic/advisory only and every proposed action remains unexecuted.
