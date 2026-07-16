# P147-003 — Evidence and verification

Status: DONE

- Generate canonical report and bind P146/source/counters.
- Run targeted tests, Ruff, Mypy, coverage, and independent review.
- Depends on: P147-002.
- Write scope: `scripts/run_p147_qualification.py`, `evals/p147/**`, and P147
  verification wiring.
- Acceptance: all four canonical artifacts validate with the exact P147
  validators and `bash scripts/verify.sh --profile p147-release` exits zero.
- Stop: any P0-P3 finding, stale source/predecessor hash, skip/xfail, or
  authority counter.
