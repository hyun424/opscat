# P87 Supervisor Run Report Artifact Roadmap

P87 turns P86 resumable supervisor run state into a structured local report artifact. The report explains what happened, why the supervisor stopped, what remains, whether work can safely continue, and what human decision is required while preserving a strict local/mock zero-side-effect boundary.

## Tickets

- P87-001 - Model the report artifact schema with run ID, status, stop reason, terminal/non-terminal classification, audit metadata, claim boundary, and zero side-effect counters.
- P87-002 - Summarize completed, skipped, blocked, and resumable items from P86-style run state without duplicating completed items after resume.
- P87-003 - Render checkpoint timelines that preserve cursor, completed item IDs, skipped item IDs, and checkpoint events.
- P87-004 - Classify safety gates hit for evidence insufficiency, approval blocked, sandbox blocked, failure streak, budget limit, and max iterations.
- P87-005 - Emit next recommended action, wakeup metadata, and human decision required sections for each run.
- P87-006 - Add deterministic fixture scenarios for completed_all, max_iteration, needs_human, failed_guardrail, no_safe_work, and resumed-run reports.
- P87-007 - Add CLI JSON/Markdown smoke output and wire the smoke into `scripts/verify.sh` plus release evidence.
- P87-008 - Publish conservative final documentation that frames P87 as a local/mock report artifact, not unattended production operation.

## Boundary

P87 is a local/mock report artifact only. It consumes modeled P86-style run state and deterministic fixture data. P87 does not call live APIs, read credentials, call networks, execute shell commands, spawn processes or agents, mutate production, execute remediation, execute actions, or claim unattended production operation.
