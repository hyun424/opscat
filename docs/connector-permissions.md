# Connector Permissions

OpsCat connector setup is local/mock in P6. auth is deferred, so connector permission preview uses the same local-header demo identity as the rest of the OSS quickstart.

Use the catalog endpoint before configuring any local secret:

## GET /connectors

```bash
curl -s http://localhost:8000/connectors \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin'
```

## Safety rules

- No broad provider tokens.
- No real external side effects.
- No production mutation by default.
- Secrets are never returned by the catalog.
- Write-like connectors are dry-run-only previews in the current local/mock build.

## Current connectors

### fake.observability

- Capabilities: `events.read`, `metrics.read`
- Risk: `read_only`
- Required role: `viewer`
- Required secret: none
- Side effects: none

### sentry.readonly

- Capabilities: `issues.read`, `issue.events.read`, `health.check`
- Risk: `read_only`
- Required role: `viewer`
- Required secret name: `sentry.token` only for opt-in `provider_mode=real` reads; fixture reads and `health.check` fixture state do not require credentials
- Default mode: `fixture`; reads sanitized recorded fixtures, performs no network I/O, and returns bounded pagination metadata
- Health states: `fixture_ok`, `missing_secret`, `invalid_config`, `rate_limited`, and `provider_error`
- Provider-shaped errors: real-mode rate limits and provider failures normalize to redacted error classes with bounded `retry_after_seconds`
- Side effects: none; real-provider mode is read-only and opt-in via local secrets

Minimum Sentry permission for future real-mode local experiments is project/organization issue and event read access only. Do not use broad admin tokens, organization owner tokens, or tokens that can mutate projects, releases, alerts, users, or billing. If the token/config is absent, invalid, rate-limited, or the provider fails, OpsCat fails closed and records redacted connector evidence/audit metadata.

### prometheus.readonly

- Capabilities: `health.check`, `query.instant`, `query.range`
- Risk: `read_only`
- Required role: `viewer`
- Required secret: none in P96; auth remains deferred
- Default mode: `fixture`; no network I/O
- Real mode: explicit `provider_mode=real` or `scripts/probe_prometheus.py --mode real`
- Endpoint source: trusted process configuration through `OPSCAT_PROMETHEUS_BASE_URL`, never a connector request payload
- Destination policy: exact `OPSCAT_PROMETHEUS_ALLOWED_HOSTS` match; HTTPS required outside loopback
- Query policy: bounded query length, range duration, sample points, series, response bytes, and timeout
- Side effects: none; GET-only reads from `/api/v1/query` and `/api/v1/query_range`

Use a Prometheus account or gateway policy that can query metrics only. Do not grant configuration, rule, target, alert-manager, admin, remote-write, or delete access. P96 does not add bearer-token auth; protected deployments remain blocked until a later scoped secret-integration ticket.

### slack.wake_up

- Capabilities: `messages.write`
- Risk: `external_message`
- Required role: `operator`
- Required secret: none in the local preview path
- Side effects: no real Slack send; dry-run preview only

### github.issues

- Capabilities: `issues.write`
- Risk: `external_write`
- Required role: `operator`
- Approval: required
- Required secret: none in the local preview path
- Side effects: no real GitHub issue creation; dry-run preview only

## Adding connectors

New connectors must include explicit capability metadata: `read_only`, `risk_level`, `required_role`, `requires_approval`, and `required_secret_name`. They must add tests and connector eval coverage before being treated as release evidence.

## Connector authoring

See [`docs/connector-sdk.md`](connector-sdk.md) and `examples/connectors/example_connector.py` for a fixture-backed connector template.
