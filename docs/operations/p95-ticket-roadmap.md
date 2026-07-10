# OpsCat P95 Ticket Roadmap — Clean-Clone Reproducibility Gate

P95 proves the repository can be cloned fresh from the private GitHub remote and run by a new contributor without hidden local state, production credentials, customer data, or untracked files. It also records the quickstart bug found during the clean-clone test and the fix that made local/mock secrets safe for `OPSCAT_MODE=local-mock`.

Boundary: P95 uses a private GitHub clean clone only for reproducibility verification. It performs no auth feature work, no live provider APIs, no production credentials, no customer logs, no production mutation, and no real remediation/action execution.

- P95-001 — Private clean clone: clone `https://github.com/hyun424/opscat` into a fresh `/private/tmp` directory and verify the cloned tree has no `.env`, `.DS_Store`, `.venv`, or `opscat.db` before setup.
- P95-002 — Contributor quickstart: run `cp .env.example .env`, `make install`, and `make quickstart` using only local/mock configuration.
- P95-003 — Reproducibility bug fix: fix the discovered `OPSCAT_MODE=local-mock` secret-provider mismatch so `.env.example` works without production secrets.
- P95-004 — Regression coverage: add targeted tests proving local/mock quickstart can use the safe default development secret key while production-like modes still require an explicit key.
- P95-005 — Full clean-clone verification: run `bash scripts/verify.sh --profile full` in the clean clone and record compile, lint, typecheck, pytest, smoke/eval, and coverage evidence.
- P95-006 — Release evidence closure: document the clean-clone result, pushed commit, commands, coverage, and safety boundary in release evidence and roadmap files.
