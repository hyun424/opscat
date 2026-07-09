# P85 Local Autonomous Supervisor Loop Roadmap

P85 adds a safe local/mock autonomous supervisor foundation. It repeatedly evaluates a backlog, selects only safe modeled local checks, persists checkpoints, stops on budget/risk/failure/human-review conditions, and emits resumable state. It is not a live daemon and does not claim unattended production operation.

## Tickets

- P85-001 - Model supervisor inputs: run ID, limits, resume checkpoint, backlog items, P76 evidence sufficiency, P79 sandbox decision, P80 approval automation decision, P83 outcome state, P84 next action, and modeled dry-run command names.
- P85-002 - Select only safe local/mock work when evidence, sandbox, approval, outcome, next-action, budget, and iteration gates pass.
- P85-003 - Stop deterministically on budget_exhausted, no_safe_work, needs_human, failed_guardrail, or completed_batch.
- P85-004 - Persist structured resumable state with selected item IDs, skipped item reasons, completed mock steps, next wakeup recommendation, checkpoint records, audit metadata, resumable cursor, and zero side-effect counters.
- P85-005 - Add deterministic scenarios for safe two-item batch, approval-blocked no-safe-work, failure streak exceeded, budget exhausted mid-queue, worsened outcome rollback/escalation review, and checkpoint resume without duplicate completion.
- P85-006 - Add CLI JSON/Markdown smoke output with concise counts.
- P85-007 - Wire P85 smoke into `scripts/verify.sh` and release evidence.
- P85-008 - Publish conservative final documentation that frames P85 as a local supervisor foundation, not unattended production operation.

## Safety boundary

P85 is local/mock supervisor modeling only. Dry-run command names are stored as text and are not executed. P85 does not call live APIs, read credentials, call networks, execute shell commands, spawn processes or agents, mutate production, execute remediation, execute actions, or claim unattended production operation.
