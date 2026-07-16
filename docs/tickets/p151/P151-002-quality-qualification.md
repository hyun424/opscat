# P151-002 — Sealed quality qualification

Status: DONE

- Implement leakage-safe scoring and exact metric recomputation.
- Add descriptive, redacted, non-release NVIDIA live-model report support.
- Depends on: P151-001.
- Write scope: `app/services/p151_ground_truth_quality.py` plus frozen helpers.
- Acceptance: all metric gates in the program plan pass by independent
  recomputation; top-1, lead time, and tool efficiency remain descriptive.
- Stop: truth opened before commitment, denominator ambiguity, unsafe action,
  invalid citation, or NVIDIA result affecting release status.
