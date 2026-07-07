# OpsCat Examples

These examples are local/mock only. Start the API first:

```bash
make run
```

Use safe demo headers:

```bash
-H 'X-OpsCat-Actor: demo-user@opscat.local' \
-H 'X-OpsCat-Tenant: demo' \
-H 'X-OpsCat-Workspace: demo' \
-H 'X-OpsCat-Role: admin'
```

Create a local incident from a Sentry-shaped fixture:

```bash
curl -s -X POST 'http://localhost:8000/webhooks/alerts/mock?process_now=true' \
  -H 'content-type: application/json' \
  -H 'X-OpsCat-Actor: demo-user@opscat.local' \
  -H 'X-OpsCat-Tenant: demo' \
  -H 'X-OpsCat-Workspace: demo' \
  -H 'X-OpsCat-Role: admin' \
  -d @examples/fixtures/signals/sentry_issue.json
```

Try alternative local fixtures:

```bash
curl -s -X POST 'http://localhost:8000/webhooks/alerts/mock?process_now=true' -H 'content-type: application/json' -d @examples/fixtures/signals/datadog_monitor.json
curl -s -X POST 'http://localhost:8000/webhooks/alerts/mock?process_now=true' -H 'content-type: application/json' -d @examples/fixtures/signals/loki_log_alert.json
curl -s -X POST 'http://localhost:8000/webhooks/alerts/mock?process_now=true' -H 'content-type: application/json' -d @examples/fixtures/signals/generic_webhook.json
```

All fixture files are synthetic and redacted. Do not use production credentials or customer logs in examples.
