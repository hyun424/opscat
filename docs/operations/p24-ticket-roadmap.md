# OpsCat P24 Ticket Roadmap — Proactive Risk Sentinel

P24 adds the proactive side of OpsCat: detect incident precursors before an outage fully occurs, forecast likely risk, and produce preventive action packets without executing production mutation.

Boundary: no auth, no production credentials, no hosted SaaS operation, no Kubernetes/cloud/database mutation, no unrestricted shell, no default external model/API calls, no remediation execution, and no unattended production-operation claim.

## Tickets

### P24-001 Risk signal schema
Create a local/mock schema for trend windows and risk signals.

Acceptance:
- Signals include service, metric, values, baseline, threshold, window, risk_type, and evidence IDs.
- Signal serialization redacts user-controlled text.

### P24-002 Trend detector
Detect rising, spike, saturation, depletion, no-data, and burn-rate patterns from synthetic/local windows.

Acceptance:
- Detector calculates trend, growth rate, baseline ratio, threshold distance, ETA-to-threshold, and confidence.
- Connection-pool, disk, queue, traffic, cache, and observability gaps are covered.

### P24-003 Risk forecast
Convert signals into forecast records with risk type, ETA, confidence, impact, evidence, and route.

Acceptance:
- Forecast route is preventive_review or blocked.
- Unsafe/missing evidence never becomes auto-remediation.

### P24-004 Preventive action planner
Produce safe prevention plans.

Acceptance:
- Auto-allowed actions are read-only diagnostics/report/notification draft only.
- Scaling, rollback, cleanup, DB session kill, config change, traffic routing, and shell remain approval-required or blocked.

### P24-005 Proactive scenario fixtures
Add deterministic proactive risk fixtures for pre-incident windows.

Acceptance:
- At least 12 proactive fixtures.
- Includes connection pool, disk-full ETA, queue SLA breach ETA, cache eviction before DB overload, error-budget burn, and false-positive/no-data cases.

### P24-006 CLI and report
Add CLI to run the proactive sentinel and output JSON/Markdown.

Acceptance:
- CLI writes risk forecasts and prevention plans.
- Markdown includes boundary, forecasts, prevention actions, and score.

### P24-007 Verification integration
Add smoke to `scripts/verify.sh` and release evidence contract tests.

Acceptance:
- Full verification runs P24 offline/local-mock.
- Latest report is copied to `/tmp/opscat-proactive-risk-latest.md`.

### P24-008 Release evidence
Document verified proactive risk coverage and boundaries.

Acceptance:
- P24 final summary exists.
- Roadmap and release evidence mark P24 implemented after verification.
