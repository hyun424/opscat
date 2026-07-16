# P153-002 — Staging read-only transport

Status: DONE

- Implement exact-host, HTTPS, GET-only provider transport.
- Deny redirects and enforce timeout and response byte budgets.
- Resolve only named environment-variable secrets in explicit live mode.
- Normalize Prometheus, Loki, and Sentry responses without persisting secrets.
