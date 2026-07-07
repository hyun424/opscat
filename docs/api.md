# OpsCat Local API

OpsCat's current API is local/mock and credential-free. No auth setup is required for the open-source quickstart; requests use a local-header demo identity until auth is explicitly reopened in a later phase.

## Demo identity headers

Use these headers to scope local demo calls:

```http
X-OpsCat-Actor: demo-user@opscat.local
X-OpsCat-Tenant: demo
X-OpsCat-Workspace: demo
X-OpsCat-Role: admin
```

This is a local-header demo identity, not production authentication. Do not use production credentials, customer logs, or real provider tokens in local examples.

## Health

### GET /health

```bash
curl -s http://localhost:8000/health
```

Returns service status, mode, and workspace hint.

## Mock alert ingestion

### POST /webhooks/alerts/mock

Queue a local/mock incident:

```bash
curl -s -X POST 'http://localhost:8000/webhooks/alerts/mock' \
  -H 'content-type: application/json' \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin' \
  -d @examples/fixtures/signals/sentry_issue.json
```

For synchronous demo behavior, add `?process_now=true`.

### POST /webhooks/alerts/fixture

Import a provider-shaped local fixture and normalize it into the existing incident flow. Supported providers are `sentry`, `datadog`, `loki`, and `generic`.

```bash
curl -s -X POST 'http://localhost:8000/webhooks/alerts/fixture?process_now=true' \
  -H 'content-type: application/json' \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin' \
  -d @examples/fixtures/signals/sentry_issue.json
```

## Incidents

### GET /incidents

```bash
curl -s http://localhost:8000/incidents \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

### GET /incidents/{incident_id}

```bash
curl -s http://localhost:8000/incidents/$INCIDENT_ID \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

## Approvals

### POST /approvals/{action_id}

```bash
curl -s -X POST "http://localhost:8000/approvals/$ACTION_ID" \
  -H 'content-type: application/json' \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin' \
  -d '{"decision":"approve","reason":"approve local mock action"}'
```

## Reports

### GET /incidents/{incident_id}/report

```bash
curl -s http://localhost:8000/incidents/$INCIDENT_ID/report \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

## Operator dashboard

### GET /operator

```bash
curl -s http://localhost:8000/operator \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

## Local secret metadata lifecycle

Secret setup remains local/mock and auth is deferred. Use admin local-header role for metadata-only secret setup. Responses never return plaintext or ciphertext.

### GET /secrets

```bash
curl -s http://localhost:8000/secrets \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

### PUT /secrets/{name}

```bash
curl -s -X PUT http://localhost:8000/secrets/sentry.token \
  -H 'content-type: application/json' \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin' \
  -d '{"value":"local-fixture-token","metadata":{"connector":"sentry.readonly"}}'
```

### DELETE /secrets/{name}

```bash
curl -s -X DELETE http://localhost:8000/secrets/sentry.token \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

## Night Autopilot

### POST /night-autopilot/simulate

```bash
curl -s -X POST http://localhost:8000/night-autopilot/simulate \
  -H 'content-type: application/json' \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin' \
  -d '{}'
```

## Connector catalog

### GET /connectors

Preview connector capabilities, minimum roles, required secret names, risk levels, and dry-run-only write surfaces before configuring any secret.

```bash
curl -s http://localhost:8000/connectors \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

See [`docs/connector-permissions.md`](connector-permissions.md).
