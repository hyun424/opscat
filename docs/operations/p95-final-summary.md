# OpsCat P95 Final Summary — Clean-Clone Reproducibility Gate

P95 validates OpsCat as a portfolio/product-quality repository that a reviewer can clone and run without relying on the maintainer's local machine. A fresh private GitHub clone was tested from `/private/tmp`, confirmed to contain no local secrets or generated state, installed from scratch, ran the no-auth local/mock quickstart, and passed the full release verification profile.

## Completed tickets

- P95-001 — Private clean clone: cloned `https://github.com/hyun424/opscat` into `/private/tmp/opscat-clean-clone-p95-fixed.wX7zoU/opscat` and verified HEAD `c5a187d7ef2b13e9ada0b336b8bdf6d38ed700e3`.
- P95-002 — Contributor quickstart: ran `cp .env.example .env`, `make install`, and `make quickstart`; quickstart completed with no production credentials and no auth setup.
- P95-003 — Reproducibility bug fix: fixed `LocalEncryptedSecretProvider` so `OPSCAT_MODE=local-mock` can use the safe default development secret key, matching `.env.example` and the documented quickstart.
- P95-004 — Regression coverage: added `test_local_mock_mode_allows_default_secret_key_for_quickstart` and reran secret-service, connector-eval, and OSS quickstart docs tests.
- P95-005 — Full clean-clone verification: ran `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full` in the clean clone; verification completed with coverage `80.71% >= 60.00%`.
- P95-006 — Release evidence closure: recorded P95 in `docs/release-evidence.md`, `ROADMAP.md`, and this summary.

## Verification evidence

Clean clone checks before setup:

```bash
git clone https://github.com/hyun424/opscat /private/tmp/opscat-clean-clone-p95-fixed.wX7zoU/opscat
cd /private/tmp/opscat-clean-clone-p95-fixed.wX7zoU/opscat
git rev-parse HEAD
# c5a187d7ef2b13e9ada0b336b8bdf6d38ed700e3
find . -maxdepth 2 \( -name .env -o -name .DS_Store -o -name .venv -o -name opscat.db \) -print
# no output before setup
```

Contributor path:

```bash
cp .env.example .env
UV_CACHE_DIR=/private/tmp/uv-cache make install
UV_CACHE_DIR=/private/tmp/uv-cache make quickstart
```

Observed quickstart result:

```text
Health: {'status': 'ok', 'service': 'opscat'}
OpsCat quickstart complete. No auth setup or production credentials were required.
```

Full release gate in the clean clone:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full
```

Observed result: compile, lint, typecheck, pytest, smoke/eval checks, docs checks, and coverage completed successfully; coverage gate reported `80.71% >= 60.00%`.

## Boundary

P95 is reproducibility evidence only. It does not add production auth, does not call live Sentry/GitHub/Slack/NVIDIA/provider APIs, does not read production credentials, does not use customer logs, does not mutate production, does not execute real remediation actions, and does not claim unattended production operator replacement.
