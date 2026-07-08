# OpsCat P26 Ticket Roadmap — Real Telemetry Adapter Contract

P26 creates the read-only contract layer between real-shaped observability payloads and OpsCat's incident/prevention engines. It uses fixtures shaped like Prometheus/Grafana, Datadog, and Sentry outputs, normalizes them into telemetry series/events/snapshots, converts compatible metrics into proactive `TrendWindow`s, and keeps all behavior local/mock and non-mutating.

Boundary: no auth, no production credentials, no live API calls, no hosted SaaS operation, no Kubernetes/cloud/database mutation, no unrestricted shell, no default external model/API calls, no remediation execution, and no unattended production-operation claim.

## Tickets

### P26-001 Telemetry source contract
Define `TelemetryPoint`, `TelemetrySeries`, `TelemetryEvent`, and `TelemetrySnapshot`.

Acceptance:
- Source, service, metric, timestamp, value, labels, unit, and evidence IDs are preserved.
- Duplicate timestamps are normalized deterministically.
- Payload serialization redacts sensitive fields.

### P26-002 Prometheus/Grafana fixture adapter
Read Prometheus `query_range`-style fixtures and convert them into telemetry series and proactive trend windows.

Acceptance:
- Matrix results become sorted telemetry series.
- Service/metric labels map correctly.
- TrendWindow output can run through P24/P25 sentinel.

### P26-003 Datadog fixture adapter
Read Datadog timeseries/event-style fixtures and convert them into telemetry series/events.

Acceptance:
- Points are sorted and deduplicated.
- Tags map to labels and service.
- Unit conversion is explicit.

### P26-004 Sentry fixture adapter
Read Sentry issue/event-style fixtures and convert them into telemetry events and evidence.

Acceptance:
- Issue count/frequency is represented as a telemetry series.
- Event text is redacted.
- Prompt-injection-like event payloads are not executable instructions.

### P26-005 Adapter quality tests
Add schema, redaction, evidence ID, timestamp, duplicate point, missing data, and TrendWindow compatibility tests.

Acceptance:
- Old missing adapter fails RED.
- Fixture adapters pass deterministic tests.

### P26-006 Proactive pipeline integration
Feed adapter-produced TrendWindows into proactive sentinel/calibration smoke.

Acceptance:
- Adapter output creates at least three TrendWindows.
- Sentinel output has no unsafe automatic action.

### P26-007 CLI and report
Add `scripts/run_telemetry_adapter.py` for fixture conversion and report output.

Acceptance:
- CLI supports `--source prometheus|datadog|sentry|all`.
- Writes JSON/Markdown.
- Markdown states local/mock/read-only boundary.

### P26-008 Release evidence
Document verified adapter contract, fixture coverage, pipeline compatibility, and boundaries.

Acceptance:
- P26 final summary exists.
- Roadmap and release evidence mark P26 implemented after verification.
