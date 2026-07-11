# Contributing to OpsCat

Thanks for helping make OpsCat a useful open-source agentic operations project. OpsCat is currently a local/mock system: it demonstrates safe incident automation patterns without requiring real provider credentials, production access, or auth setup.

## Start locally

```bash
uv sync --frozen --extra dev
uv run --no-sync opscat demo --output /tmp/opscat-demo-replay.json
```

Useful checks:

```bash
make quickstart
make demo
make test
make verify
```

Eval evidence:

```bash
python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md
python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md
```

## Safety rules

- No production credentials.
- Do not include secrets, tokens, private keys, customer data, or raw customer logs in issues, PRs, fixtures, docs, or tests.
- Keep new connectors fixture-backed or dry-run by default.
- Do not add real external side effects unless a future explicit ticket scopes them.
- Do not add arbitrary shell, cloud, Kubernetes, database, or production rollback mutation as a product tool.
- P5 auth is deferred: do not add login, sessions, OIDC, SSO, passwords, or CSRF/session work unless the owner explicitly reopens auth.
- Preserve local-header demo identity as the current local/mock boundary.


## Safety checklist

Before opening a PR that touches actions, connectors, incident import, approvals, policy, reports, workflow jobs, metrics, or docs, verify:

- No production credentials, real provider tokens, private keys, customer data, or raw customer logs are included.
- New connectors are fixture-backed or dry-run by default.
- Write-like behavior is approval-gated and cannot silently mutate production.
- Redaction is applied before evidence, reports, metrics, audit logs, and model/tool summaries.
- Connector eval or incident eval coverage proves the new behavior and failure mode.
- Auth remains deferred unless the project owner explicitly reopens auth work.

## Development workflow

1. Pick a ticket from `ROADMAP.md` or `docs/operations/p5-ticket-roadmap.md`.
2. Write or update tests first.
3. Confirm the relevant test is RED for the intended missing behavior.
4. Implement the smallest safe change.
5. Re-run the targeted tests.
6. Run `make verify` before claiming a release-ready change.
7. Update docs and release evidence when behavior or commands change.
8. Run the P122 security, SBOM, license, packaging, and frozen-evidence profile for release changes.

Capability claims must link to a frozen evidence artifact or an explicit limitation. Do not describe local qualification as production autonomy or operator replacement.

## Test commands

- `make test` — pytest regression suite.
- `make evals` — golden incident evals and connector safety evals.
- `make verify` — full local release gate.
- `python scripts/run_evals.py ...` — incident eval report.
- `python scripts/run_connector_evals.py ...` — connector eval report.

## Lore commit protocol

The project follows the Lore commit protocol for decision-oriented commit
messages.

Commit messages should explain why the change was made and include useful trailers when they add context:

```text
<why this change exists>

Constraint: <external constraint>
Rejected: <alternative> | <why rejected>
Confidence: <low|medium|high>
Scope-risk: <narrow|moderate|broad>
Directive: <future warning>
Tested: <commands run>
Not-tested: <known gaps>
```

## Pull request expectations

A good PR includes:

- the ticket or problem being solved;
- tests that prove the change;
- whether eval/report artifacts changed;
- safety boundary notes;
- exact commands run;
- known gaps.

If a change touches connectors, actions, policy, approvals, reports, redaction, or workflow execution, include a safety note explaining why it cannot silently mutate production or leak secrets.
