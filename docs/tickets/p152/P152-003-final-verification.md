# P152-003 — Final evidence and verification

Status: DONE

- Generate final evidence after independent P0-P3 zero review.
- Run P122, secret scan, focused coverage, and full repository verification.
- State production operator replacement remains unqualified.
- Depends on: P152-002.
- Write scope: `scripts/run_p152_qualification.py`, `evals/p152/**`, and final
  verification wiring.
- Acceptance: exact four artifacts validate; `p152-release`, P122, secret scan,
  focused coverage, `git diff --check`, and full `bash scripts/verify.sh` pass.
- Stop: any nonzero review finding, skipped gate, leaked secret, dirty generated
  evidence after replay, or production replacement claim.
