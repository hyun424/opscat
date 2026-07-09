# P86 Resumable Local Supervisor Runner Roadmap

P86 makes the P85 local autonomous supervisor contract operational as a resumable local/mock runner. It executes multiple modeled safe supervisor iterations from fixture/state data, records atomic checkpoint write plans, resumes after interruption, and stops deterministically without live side effects.

## Tickets

- P86-001 - Model the persisted runner state: run ID, cursor, completed item IDs, skipped item IDs and reasons, iteration count, failure streak, checkpoints, stop reason, next recommended wakeup, audit metadata, and zero side-effect counters.
- P86-002 - Resume from fixture state without duplicating completed items, while preserving skipped or blocked reasons.
- P86-003 - Continue from the cursor across repeated safe local/mock iterations using dry-run command names as text only.
- P86-004 - Stop deterministically on max_iterations, budget_exhausted, needs_human, failed_guardrail, no_safe_work, or completed_all.
- P86-005 - Represent atomic checkpoint persistence as temp_path to final_path metadata without writing runner state outside the requested output paths.
- P86-006 - Add deterministic fixture scenarios for fresh completion, interrupted resume, max-iteration stop, human review, guardrail failure, and terminal completed-all behavior.
- P86-007 - Add CLI JSON/Markdown smoke output and wire the smoke into `scripts/verify.sh` plus release evidence.
- P86-008 - Publish conservative final documentation that frames P86 as a local resumable runner foundation, not unattended production operation.

## Boundary

P86 is local/mock runner modeling only. Dry-run command names are stored as text and are not executed. P86 does not call live APIs, read credentials, call networks, execute shell commands, spawn processes or agents, mutate production, execute remediation, execute actions, or claim unattended production operation.
