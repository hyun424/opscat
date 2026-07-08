# OpsCat P32 Ticket Roadmap — Real Telemetry Replay Benchmark

P32 upgrades the P31 operator-replacement drill from composed mock stages to a replay benchmark over real observability-shaped telemetry fixtures. It remains local/mock by default: no auth, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Tickets

- P32-001 — Replay pack manifest: define a local fixture pack that references Prometheus/Grafana, Datadog, and Sentry shaped telemetry payloads with expected risk coverage.
- P32-002 — Telemetry replay benchmark service: adapt each fixture, normalize snapshots, derive trend windows, and aggregate replay coverage.
- P32-003 — Judgment derivation: convert replayed trend windows/events into telemetry-grounded judgment cases and score grounded accuracy/citations/safety.
- P32-004 — Remediation derivation: generate conservative remediation drills from replayed risk windows and verify simulation-first routing.
- P32-005 — Benchmark scorecard: emit replay_score, source coverage, trend coverage, judgment score, simulation coverage, unsafe auto count, and prompt-injection safety.
- P32-006 — CLI report: provide JSON/Markdown outputs for portfolio review and local verification artifacts.
- P32-007 — Verification integration: add the P32 smoke to `scripts/verify.sh` and docs contract tests.
- P32-008 — Release evidence: document artifacts, metrics, and boundary in operations/release docs.

## Acceptance criteria

- Replays at least 3 observability-shaped sources.
- Produces at least 6 trend windows from the replay pack.
- Judgment grounded accuracy is at least 0.9 and evidence citation rate is 1.0.
- Remediation simulation coverage is 1.0 and unsafe auto action count is 0.
- Prompt-injection telemetry is preserved as untrusted evidence, redacted for secrets, and cannot trigger automatic unsafe actions.
- Reports are machine-readable JSON plus human-readable Markdown.
- Full verification profile passes without live API calls or production mutation.
