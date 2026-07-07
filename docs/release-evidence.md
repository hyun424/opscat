# OpsCat P4 Release Evidence Index

This index maps the P4 portfolio claim to the exact local commands, tests, generated artifacts, and safety boundaries that support it.

## Primary release gate

Run the full local release gate:

```bash
bash scripts/verify.sh
```

The gate currently runs:

1. Python bytecode compile for `app`, `tests`, and `scripts`.
2. Ruff lint for `app`, `tests`, and `scripts`.
3. Mypy typecheck for `app`, `tests`, and `scripts`.
4. Full pytest regression suite.
5. Coverage gate via `scripts/coverage_gate.py`.
6. Golden incident evals via `scripts/run_evals.py`.
7. Connector eval runner via `scripts/run_connector_evals.py`.
8. Local deterministic demo smoke.
9. Docker Compose config validation.
10. Tracked generated artifact scan.
11. Whitespace diff check.


## Verification profiles

Use named profiles when running locally or in CI:

```bash
bash scripts/verify.sh --profile fast
bash scripts/verify.sh --profile full
bash scripts/verify.sh --profile eval
bash scripts/verify.sh --profile docs
```

- `fast`: compile, lint, typecheck, and pytest.
- `full`: complete release gate; this remains the default when no profile is supplied.
- `eval`: golden incident evals plus connector evals.
- `docs`: documentation contract tests plus repository hygiene checks.

GitHub Actions runs the secret-free full profile from `.github/workflows/ci.yml`.

## P4 evidence artifacts

| Claim | Gate | Artifact |
| --- | --- | --- |
| Incident agent loop is reproducibly evaluated | `scripts/run_evals.py` | `/tmp/opscat-evals-latest.md`, `/tmp/opscat-evals.json` |
| Connector calls fail closed and preserve idempotency | `scripts/run_connector_evals.py` | `/tmp/opscat-connector-evals-latest.md`, `/tmp/opscat-connector-evals.json` |
| P5 connector product readiness covers setup, permissions, secret lifecycle, and incident import normalization | `tests/test_connector_evals.py` + `scripts/run_connector_evals.py` | connector eval JSON/Markdown categories: `setup_permission`, `setup_failure`, `import_normalization` |
| Dashboard is navigable and safe enough for demo review | `tests/test_operator_dashboard_e2e.py` | pytest output |
| Golden corpus coverage cannot silently narrow | `tests/test_eval_coverage_taxonomy.py` | `docs/eval-taxonomy.json` |
| Reviewer-facing narrative is stable | `tests/test_portfolio_evidence_docs.py` | `docs/eval-report.md` |
| Release evidence map is stable | `tests/test_release_evidence_index.py` | `docs/release-evidence.md` |

## Manual artifact commands

Golden incident evals:

```bash
python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md
```

Connector evals:

```bash
python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md
```

Dashboard browser-contract E2E:

```bash
pytest tests/test_operator_dashboard_e2e.py -q
```

Taxonomy and portfolio docs:

```bash
pytest tests/test_eval_coverage_taxonomy.py tests/test_portfolio_evidence_docs.py tests/test_release_evidence_index.py -q
```

## Safety boundary

No real external side effects are permitted in P4.

- No real Slack/GitHub/Sentry side effects.
- No production rollback.
- No Kubernetes/cloud/database/shell mutation product tool.
- No real customer data.
- No production credentials.

The P4 evidence demonstrates the local/mock architecture and release discipline. P5 must add production authentication, real connector deployment, credential/OAuth operations, CI, hosted workflow workers, real incident replay, load/soak testing, and security review before paid customer production use.
