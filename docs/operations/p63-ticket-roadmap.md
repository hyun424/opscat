# OpsCat P63 Ticket Roadmap — Staging Live Read-only Preflight Runner

P63 adds the last safety gate before connecting OpsCat to real staging observability APIs. Default execution remains no-live. A live staging GET preflight is only eligible when the connector passed P62, host allowlist matches, method is GET, query budget is safe, environment is staging, credential refs are indirect, and an explicit live flag plus manual approval are present.

## Tickets

- P63-001 — Preflight fixture: define provider-shaped staging GET checks mapped to P62 connector IDs plus an unsafe blocked check.
- P63-002 — Default no-live runner: evaluate eligibility while making zero network/API calls unless live staging is explicitly enabled.
- P63-003 — Live staging gates: require `--live-staging`, manual approval, allowlisted host, GET-only method, staging environment, P62-ready connector, and safe query budget.
- P63-004 — Mock transport contract: test live-path behavior through an injected mock transport without real network calls.
- P63-005 — Safety counters: report attempted GET count, live API call count, blocked check count, production mutation count, action execution count, and non-GET count.
- P63-006 — Redaction: never expose raw credential values or authorization headers in reports.
- P63-007 — CLI smoke: emit JSON and Markdown reports in default no-live mode.
- P63-008 — Release evidence: wire docs, verification, and full-profile evidence.

## Acceptance criteria

- Default CLI/no-live mode performs zero live API calls and zero preflight attempts.
- Mock live mode performs only GET checks for P62-ready staging connectors on allowlisted hosts.
- Unsafe production/admin/non-GET/disallowed-host checks are blocked.
- No real server connection is required in normal verification.
- The report gives a clear next step for manually approved staging read-only attachment.
