# Contributing to OpsCat

Thanks for helping make OpsCat a useful open-source agentic operations project. OpsCat is currently a local/mock system: it demonstrates safe incident automation patterns without requiring real provider credentials, production access, or auth setup.

## Start locally

```bash
cp .env.example .env
make install
make quickstart
```

Useful checks:

```bash
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

## Development workflow

1. Pick a ticket from `ROADMAP.md` or `docs/operations/p5-ticket-roadmap.md`.
2. Write or update tests first.
3. Confirm the relevant test is RED for the intended missing behavior.
4. Implement the smallest safe change.
5. Re-run the targeted tests.
6. Run `make verify` before claiming a release-ready change.
7. Update docs and release evidence when behavior or commands change.

## Test commands

- `make test` — pytest regression suite.
- `make evals` — golden incident evals and connector safety evals.
- `make verify` — full local release gate.
- `python scripts/run_evals.py ...` — incident eval report.
- `python scripts/run_connector_evals.py ...` — connector eval report.

## Lore commit protocol

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
