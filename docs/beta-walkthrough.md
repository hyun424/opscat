# 10-Minute Beta Walkthrough

This walkthrough lets a beta reviewer experience OpsCat as a local/mock agentic operations product: inspect connector permissions, configure a fixture connector secret, import a realistic fixture incident, review an action, approve or reject through the API, read the report, and simulate the morning report.

No auth setup is required. OpsCat uses local-header demo identity in P5; auth is deferred and the system is not production-ready.

## 0. Start locally

```bash
cp .env.example .env
make install
make run
```

Use these headers in another terminal:

```bash
export OPSCAT_HEADERS=(
  -H 'X-OpsCat-Actor: demo-user@opscat.local'
  -H 'X-OpsCat-Tenant: demo'
  -H 'X-OpsCat-Workspace: demo'
  -H 'X-OpsCat-Role: admin'
)
```

## 1. Preview connector permissions

```bash
curl -s http://localhost:8000/connectors "${OPSCAT_HEADERS[@]}"
```

Expected local API surface: `GET /connectors` returns connector capability metadata, required roles, risk levels, required secret names, and dry-run-only write surfaces.

## 2. Configure fixture connector secret metadata

```bash
curl -s -X PUT http://localhost:8000/secrets/sentry.token \
  -H 'content-type: application/json' \
  "${OPSCAT_HEADERS[@]}" \
  -d '{"value":"local-fixture-token","metadata":{"connector":"sentry.readonly"}}'
```

The local API surface is `PUT /secrets/sentry.token`.

This is a local fixture token only. Do not use production credentials or customer data.

## 3. Import a fixture incident

```bash
curl -s -X POST 'http://localhost:8000/webhooks/alerts/fixture?process_now=true' \
  -H 'content-type: application/json' \
  "${OPSCAT_HEADERS[@]}" \
  -d @examples/fixtures/signals/sentry_issue.json
```

The local API surface is `POST /webhooks/alerts/fixture`. Save the returned incident/action IDs:

```bash
export INCIDENT_ID='<copy incident id>'
export ACTION_ID='<copy action id>'
```

## 4. Review action in the operator console

Open or curl the read-only action preview:

```bash
curl -s http://localhost:8000/operator/actions/$ACTION_ID "${OPSCAT_HEADERS[@]}"
```

The local UI surface is `GET /operator/actions/`. It shows risk, policy, preconditions, post-checks, evidence IDs, and approval API instructions. It intentionally does not render browser mutation forms while auth is deferred.

## 5. Approve or reject through the API

Approve:

```bash
curl -s -X POST http://localhost:8000/approvals/$ACTION_ID \
  -H 'content-type: application/json' \
  "${OPSCAT_HEADERS[@]}" \
  -d '{"decision":"approve","reason":"local beta walkthrough approval"}'
```

Reject instead:

```bash
curl -s -X POST http://localhost:8000/approvals/$ACTION_ID \
  -H 'content-type: application/json' \
  "${OPSCAT_HEADERS[@]}" \
  -d '{"decision":"reject","reason":"local beta walkthrough rejection"}'
```

The API surface is `POST /approvals/`.

## 6. Read incident and report

```bash
curl -s http://localhost:8000/incidents/$INCIDENT_ID "${OPSCAT_HEADERS[@]}"
curl -s http://localhost:8000/incidents/$INCIDENT_ID/report "${OPSCAT_HEADERS[@]}"
```

The API surface is `GET /incidents/` and `GET /incidents/{incident_id}/report`.

## 7. Simulate sleep-time operation

```bash
curl -s -X POST http://localhost:8000/night-autopilot/simulate \
  -H 'content-type: application/json' \
  "${OPSCAT_HEADERS[@]}" \
  -d '{"allowed_services":["worker"],"allowed_environments":["staging"],"max_automatic_risk":"low"}'
```

The API surface is `POST /night-autopilot/simulate`. The morning report explains detected, resolved, escalated, blocked, verification, and follow-up counts.

## 8. Verify the release gate

```bash
bash scripts/verify.sh --profile full
```

Review local evidence:

- `docs/release-evidence.md`
- `docs/connector-permissions.md`
- `docs/deployment-dry-run.md`
- `/tmp/opscat-evals-latest.md`
- `/tmp/opscat-connector-evals-latest.md`

## Production-readiness boundary

This walkthrough is local/mock only and not production-ready. Before real customer use, OpsCat still needs production auth, tenant administration, external secret management, real connector deployment, hosted workers, load/soak tests, and a security review.

## P6 agentic loop walkthrough

Run `uv run --no-sync --extra dev python scripts/demo_agentic_loop.py`, then open `/operator/incidents/{INCIDENT_ID}` from the printed output to inspect the seven-stage trace and approval-gated action evidence.
