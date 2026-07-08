# OpsCat P66 Ticket Roadmap — Autonomous Day Loop Backlog

P66 gathers the next large set of OpsCat work into a safe autonomous backlog and generates a day-long execution loop plan. The loop is planning/verification only by default: no live API calls, no credential reads, no network calls, no production mutation, and no remediation execution.

## Tickets

- P66-001 — Long-horizon backlog: define P66-P90 ticket candidates spanning live attach, ingestion, monitoring, evaluation, action safety, UX, packaging, and release hardening.
- P66-002 — Safety classifier: classify each ticket as safe-local, gated-live, gated-action, or blocked-production.
- P66-003 — Dependency scheduler: order tickets by prerequisites and block live/action work until explicit evidence exists.
- P66-004 — Day-loop planner: generate a 24-hour dry-run loop with bounded cycles, batch size, verification commands, and checkpoint cadence.
- P66-005 — Auto-run contract: emit machine-readable next-step batches that an external agent/team can consume without enabling dangerous actions.
- P66-006 — Evidence ledger: report backlog counts, runnable counts, blocked counts, validation commands, and hard-zero side-effect counters.
- P66-007 — CLI smoke: emit JSON and Markdown reports for the autonomous day loop plan.
- P66-008 — Release evidence: wire docs, verification, and full-profile evidence.

## Acceptance criteria

- At least 25 future tickets are gathered.
- The first runnable batch is entirely local/offline and excludes live credentials, network calls, and production actions.
- Live/action tickets are retained but gated, not dropped.
- The generated day loop contains bounded cycles and verification checkpoints.
- Reports include exact safety counters and no secret leakage.
