# OpsCat P25 Ticket Roadmap — Proactive Signal Corpus Expansion and Calibration

P25 turns the P24 proactive sentinel from a small proof-of-concept into a calibrated pre-incident evaluation bench. It expands proactive fixtures to 100+ cases, adds expected outcome metadata, scores ETA/route/confidence/action safety, reports risk-type coverage, and keeps all prevention behavior local/mock and non-mutating.

Boundary: no auth, no production credentials, no hosted SaaS operation, no Kubernetes/cloud/database mutation, no unrestricted shell, no default external model/API calls, no remediation execution, and no unattended production-operation claim.

## Tickets

### P25-001 Proactive taxonomy
Define broad proactive risk taxonomy with at least 30 risk types across resource exhaustion, DB, queue, SLO, deploy, dependency, observability, security, data pipeline, and false-positive/noise cases.

Acceptance:
- At least 30 distinct risk types.
- At least 10 high-priority operational families represented.

### P25-002 Fixture expansion
Expand `evals/proactive/seed/risk_windows.json` from 12 to at least 100 deterministic local/mock windows.

Acceptance:
- At least 100 fixtures.
- Unique IDs.
- Every fixture has evidence, baseline, threshold, values, suggested approval actions, blocked actions, and expected outcome metadata.

### P25-003 Expected outcome schema
Add expected outcome fields for route, ETA range, minimum confidence, expected auto capabilities, approval-required capabilities, and blocked capabilities.

Acceptance:
- Fixture loader parses expected outcomes.
- Missing expected outcomes fail tests.

### P25-004 Calibration evaluator
Score proactive forecasts against expected route, ETA range, confidence floor, auto action safety, approval route, and blocked route.

Acceptance:
- Evaluator reports mismatch counts and per-risk-type coverage.
- Unsafe auto actions fail calibration.

### P25-005 Calibration report CLI
Add a CLI that runs proactive sentinel calibration and writes JSON/Markdown.

Acceptance:
- Report includes total windows, pass/fail, risk type count, route mismatch count, ETA out-of-range count, confidence failure count, unsafe auto action count, and coverage table.

### P25-006 Verification integration
Add P25 smoke and release evidence tests to verification.

Acceptance:
- Full verification runs P25 offline/local-mock.
- Latest report is copied to `/tmp/opscat-proactive-calibration-latest.md`.

### P25-007 Release evidence
Document scenario count, risk-type coverage, calibration results, verification, and boundaries.

Acceptance:
- P25 final summary exists.
- Roadmap and release evidence mark P25 implemented after verification.
