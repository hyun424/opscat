# Post-P131 Autonomy Roadmap

## Goal

Advance OpsCat from a credential-free local JSONL monitor into an
evidence-bound incident-response agent without skipping authority, durability,
or evaluation gates. Each phase uses plan -> independent plan review -> tests
first -> implementation -> independent code review -> release verification.

Auth remains deferred. The default path remains credential-free and fail
closed. A later phase may define a reviewed read-only observation authority,
but no phase silently converts observation permission into action authority.

## Dependency order

### P132 - Supervised Runtime Endurance Qualification

Harden and qualify the real P131 process: graceful signals, bounded report
retention, disk-pressure failure, external-process restart, lease conflict,
restart backoff, and deployment templates. This is local single-host evidence,
not a 24/7 production SLO.

### P133 - Local Dead-Man Notification Outbox

Turn unhealthy watchdog and readiness results into redacted, durable local
notification drafts with evidence references. P133 sends no email, webhook,
Slack message, page, or network request.

### P134 - Observation Authority Contract

Separate observation authority from action authority. Define explicit levels,
host/method/capability budgets, counters, receipts, and fail-closed review gates
before any new live read-only source is enabled.

### P135 - Provider-Shaped Export Attachment

Accept credential-free Prometheus, Loki, Grafana, Sentry, and OpenTelemetry
exports from allowlisted local artifacts, normalize them, and bind provenance.
No provider SDK or live request is introduced.

### P136 - Opt-in Read-only Live Shadow Preflight

Build a default-off, allowlisted, GET-only, bounded live-shadow contract and a
mock transport conformance suite. Real credentials and production targets
remain blocked until an explicit later review.

### P137 - Always-on Evidence Investigation Loop

Connect fresh monitor observations to the existing bounded diagnostic,
hypothesis, evidence-gap, and judgment pipeline. The output is an incident
episode, cited hypotheses, proposed read-only acquisitions, and a simulated
response plan. Deterministic policy retains all action authority.

### P138 - Controlled Response Readiness Dossier

Aggregate durability, judgment, safety, rollback, approval, tenancy, secret,
and audit gaps into an explicit go/no-go dossier for a future controlled-action
phase. P138 is a gate; it grants no production mutation or operator-replacement
claim.

## Cross-phase stop conditions

- Missing or stale evidence, malformed receipts, counter ambiguity, or source
  tamper fails closed.
- Default verification performs no credential read or external network call.
- Runtime action, mutation, free-form command, and authority-escape counters
  remain exact integer zero until a separately reviewed phase changes a named
  contract.
- Synthetic, accelerated, local, or staging evidence is never relabeled as
  production effectiveness or 24/7 availability.
- Every promoted artifact is reproducible, hash-bound, and independently
  reviewable.
