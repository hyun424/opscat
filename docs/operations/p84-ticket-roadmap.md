# P84 Outcome-Driven Next Action Planner Roadmap

P84 converts P83 post-action outcomes into the next safest local/mock operator plan: stop, keep watching, gather evidence, escalate, prepare rollback review, update communications, or block an unsafe path. It does not execute actions, rollbacks, communications, shell commands, API calls, or production mutations.

## Tickets

- P84-001 - Model next-action inputs from P83 outcome decisions, P76 evidence sufficiency, P80 approval decision, P81 rollback draft state, P82 communication draft state, P77 recovery proof, blast radius, reversibility, timing, guardrails, and evidence references.
- P84-002 - Add deterministic planner decisions: stop_resolved, keep_watching, gather_more_evidence, escalate_to_human, prepare_rollback_review, update_comms_draft, and block_unsafe_path.
- P84-003 - Return selected action, rationale, required evidence, human approval requirement, communication update requirement, rollback promotion flag, wait/recheck window, guardrails, and audit metadata.
- P84-004 - Preserve zero side effects with counters for action execution, live API calls, credential reads, network calls, production mutation, shell execution, rollback execution, message sending, and ticket creation.
- P84-005 - Add deterministic fixture scenarios for resolved, improving, unchanged DB saturation window exceeded, worsened mitigation, inconclusive/noisy telemetry, and unsafe blocked action.
- P84-006 - Add CLI JSON/Markdown smoke output for local/mock planner reports.
- P84-007 - Wire P84 smoke into `scripts/verify.sh` and release evidence.
- P84-008 - Publish conservative final summary without claiming unattended production operation.

## Safety boundary

P84 is planner-only and local/mock. It may recommend human review, evidence collection, rollback draft review, or communication draft updates, but it never performs external effects or claims unattended production operation.
