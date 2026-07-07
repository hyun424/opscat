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


## Versioned release evidence snapshot

Before tagging or publishing an OSS snapshot, run the full local gate:

```bash
bash scripts/verify.sh --profile full
```

This versioned release evidence snapshot should reference:

- `docs/release-evidence.md`;
- `CHANGELOG.md`;
- `docs/deployment-dry-run.md`;
- `/tmp/opscat-evals-latest.md`;
- `/tmp/opscat-connector-evals-latest.md`;
- the current git commit SHA.

stable vs experimental status is documented in `CHANGELOG.md` and `docs/deployment-dry-run.md`.

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

## P5 final release evidence

P5 final release evidence was closed with the local/mock OSS productization scope complete and auth remains deferred. The final gate is:

```bash
bash scripts/verify.sh --profile full
```

Expected terminal evidence includes `Verification complete (full)`.

Completed P5 tickets:

- P5-001
- P5-002
- P5-003
- P5-004
- P5-005
- P5-006
- P5-007
- P5-008
- P5-009
- P5-010
- P5-011
- P5-012
- P5-013
- P5-014
- P5-015
- P5-016
- P5-017
- P5-018

P5 remains local/mock: no production credentials, live provider mutation, hosted auth, or real customer production deployment is claimed.

## P6 Agentic Loop Evidence

- Roadmap: `docs/operations/p6-ticket-roadmap.md`
- Final summary: `docs/operations/p6-final-summary.md`
- Agentic loop docs: `docs/agentic-loop.md`
- Demo command: `uv run --no-sync --extra dev python scripts/demo_agentic_loop.py`
- Agentic eval command: `python scripts/run_agentic_evals.py --output-json /tmp/opscat-agentic-evals.json --output-md /tmp/opscat-agentic-evals.md`
- Latest temp eval artifact: `/tmp/opscat-agentic-evals-latest.md`
- Security review: `docs/security-review-p6.md`
- Safety policy: `docs/operations/safety-policy.md`
- Verification command: `bash scripts/verify.sh --profile full`

P6 keeps auth deferred and does not claim production readiness or unattended production mutation safety.

## P7 Reliability & Safety Lab Evidence

- Roadmap: `docs/operations/p7-ticket-roadmap.md`
- Final summary: `docs/operations/p7-final-summary.md`
- Security review: `docs/security-review-p7.md`
- Replay command: `python scripts/run_replay_evals.py --output-json /tmp/opscat-replay-evals.json --output-md /tmp/opscat-replay-evals.md`
- Targeted P7 tests: `pytest -q tests/test_p7_reliability_lab.py`
- Full release gate: `bash scripts/verify.sh --profile full`

P7 remains local/mock and auth-deferred. It adds replay, adversarial evals, confidence calibration, self-critique, blast-radius classification, action simulation, incident memory, Night Autopilot v2 gates, failure-mode reporting, and reliability dashboard metrics without claiming unattended production operation.
