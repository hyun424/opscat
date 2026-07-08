# OpsCat P55 Ticket Roadmap — Candidate Benchmark Promotion Gate

P55 promotes the P54 improved derived benchmark view into a versioned candidate benchmark pack while preserving the P51 baseline fixture as the immutable regression reference.

## Tickets

- P55-001 — Baseline reference lock: compute a stable SHA-256 fingerprint for the P51 source fixture and mark it as `preserved_reference_only`.
- P55-002 — Candidate pack emission: package the improved P54 derived cases with version, source reference, stable candidate fingerprint, and promotion metadata.
- P55-003 — Promotion gates: require evidence-gap closure, recovery-verification-gap closure, positive score deltas, baseline preservation, and zero unsafe/live/production counters.
- P55-004 — Regression command manifest: include exact local commands required to compare baseline, improved view, and candidate promotion gate.
- P55-005 — CLI report: write JSON and Markdown artifacts for local/offline review.
- P55-006 — Verification integration: wire a P55 smoke check into `scripts/verify.sh`.
- P55-007 — Release evidence: document P55 artifacts, boundary, and final verification result.

## Acceptance criteria

- The P51 fixture is not modified.
- Candidate pack contains four cases and at least two improved cases.
- Promotion gates pass only when evidence_gap is 1→0 and recovery_verification_gap is 2→0.
- Evidence-quality and recovery-verification score deltas are positive.
- Unsafe auto-execute, production execution, and live calls remain zero.
- Boundaries remain offline/local: no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
