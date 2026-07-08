# OpsCat P65 Ticket Roadmap — Real Staging Read-only Dry Attach

P65 introduces the real-staging attachment plan without performing real network calls or reading `.env`. It validates provider endpoint references, secret provider references, audit handoff, and rollback/detach safety before a future explicitly approved live attach.

## Tickets

- P65-001 — Dry attach fixture: define real-staging-shaped Grafana, Sentry, and Datadog attachments plus unsafe blocked attachment.
- P65-002 — Secret provider contract: support explicit `provider://namespace/key` refs and block raw credentials and direct `.env` reads.
- P65-003 — Endpoint contract: require HTTPS, staging environment, allowlisted host, provider match, and GET-only health probe.
- P65-004 — P64 audit handoff: require P64 approved dry-run requests and audit entries before an attachment becomes attach-ready.
- P65-005 — Detach plan: generate safe detach/disable polling plan without mutating production or provider state.
- P65-006 — Redaction: expose only credential ref fingerprints and endpoint hosts; no raw tokens, auth headers, or secret values.
- P65-007 — CLI smoke: emit JSON and Markdown dry-attach report with zero network calls.
- P65-008 — Release evidence: wire docs, verification, full-profile evidence, and safety counters.

## Acceptance criteria

- At least three real-staging-shaped provider attachments are attach-ready in dry-run mode.
- Unsafe production/raw credential attachment is blocked.
- No `.env` read, real credential read, real network call, production mutation, or action execution occurs.
- Every attach-ready provider has a detach plan and audit handoff.
- Reports include exact counters and no secret leakage.
