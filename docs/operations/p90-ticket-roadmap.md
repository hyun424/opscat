# P90 Safe Auto-Run Readiness Gate Roadmap

P90 evaluates whether a P89 safe local auto-run result is ready for longer unattended local operation, supervised shadow operation, or human-gated staging dry-run operation. It consumes modeled P89 entrypoint output plus P76 evidence sufficiency, P79 sandbox safety, P80 approval policy, P83/P84 closed-loop outcome, P87 reportability, and P88 scheduler stop-reason evidence.

## Tickets

- P90-001 - Model the readiness result schema with readiness level, numeric score, component scores, pass/fail gates, blockers, required next capabilities, allowed operating mode, forbidden claims, audit metadata, and zero side-effect counters.
- P90-002 - Consume deterministic P89-style entrypoint results and prior P76/P79/P80/P83/P84/P87/P88 safety evidence without live APIs, credentials, network calls, shell execution, action execution, or production mutation.
- P90-003 - Add pass/fail gates for evidence, approval safety, sandbox safety, resume safety, reportability, bounded scheduling, zero side effects, human handoff, and failure handling.
- P90-004 - Score readiness conservatively into not_ready, local_dry_run_ready, supervised_shadow_ready, human_gated_staging_ready, or blocked.
- P90-005 - Emit blockers, warnings, required next capabilities, allowed operating mode, and forbidden claims that prevent production/operator-replacement overclaiming.
- P90-006 - Add deterministic fixture scenarios for clean local dry-run, resumable incomplete, needs-human, failed guardrail, missing report/evidence, and nonzero side-effect counters.
- P90-007 - Add CLI JSON/Markdown smoke output and wire the smoke into `scripts/verify.sh` plus release evidence.
- P90-008 - Publish conservative release documentation that frames P90 as safe local/shadow readiness evaluation, not production unattended approval.

## Boundary

P90 is a local/mock readiness gate only. It models readiness from fixture evidence and P89-style data. P90 does not call live APIs, read credentials, call networks, execute shell commands, sleep, spawn processes or agents, mutate production, execute remediation, execute actions, or claim unattended production operation or operator replacement approval.
