# P151-003 — Evidence and verification

Status: DONE

- Generate P151 report and bind P150/corpus/predictions/truth/counters.
- Run targeted tests, static checks, coverage, and independent review.
- Depends on: P151-002.
- Write scope: `scripts/run_p151_qualification.py`, `evals/p151/**`, and P151
  verification wiring.
- Acceptance: exact four artifacts validate, 48/48 rows score, and
  `p151-release` exits zero.
- Stop: nonzero review finding, stale P150/corpus binding, metric mismatch, or
  authority counter.
