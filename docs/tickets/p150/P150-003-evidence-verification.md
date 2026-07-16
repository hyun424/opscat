# P150-003 — Evidence and verification

Status: DONE

- Generate P150 report and bind P149/profile/schedule/counters.
- Run targeted tests, static checks, coverage, and independent review.
- Depends on: P150-002.
- Write scope: `scripts/run_p150_qualification.py`, `evals/p150/**`, and P150
  verification wiring.
- Acceptance: exact four artifacts validate and `p150-release` exits zero.
- Stop: nonzero review finding, stale P149 binding, resource-gate failure, or
  authority counter.
