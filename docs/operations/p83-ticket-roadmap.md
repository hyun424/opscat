# P83 Post-Action Outcome Monitor Roadmap

P83 closes the local/mock incident-response loop by judging whether a proposed or mock-applied action improved the incident, resolved it, left it unchanged, worsened it, lacks enough evidence, or is unsafe to continue. It does not execute actions, rollbacks, communications, shell commands, API calls, or production mutations.

## Tickets

- P83-001 - Model post-action inputs: incident id, action/draft id, pre-action signals, post-action signals, expected recovery proof, evidence sufficiency, rollback PR draft status, Slack/ticket draft status, elapsed/window timing, and guardrails.
- P83-002 - Compute deterministic metric and log deltas across pre/post evidence windows.
- P83-003 - Classify outcomes as resolved, improving_keep_watching, unchanged_investigate, worsened_rollback_or_escalate, inconclusive_need_more_evidence, or blocked_unsafe_to_continue.
- P83-004 - Return conservative confidence, evidence references, missing evidence, next recommended step, communication update guidance, rollback human-review promotion guidance, and audit metadata.
- P83-005 - Preserve zero side effects: no live APIs, credentials, network, shell execution, production mutation, remediation execution, rollback execution, message sending, ticket creation, or action execution.
- P83-006 - Add deterministic fixture scenarios for improving restart, mock rollback resolution, unchanged DB saturation, worsened mitigation, noisy incomplete telemetry, and unsafe blocked action.
- P83-007 - Add CLI JSON/Markdown smoke output and wire it into `scripts/verify.sh`.
- P83-008 - Publish release evidence and final summary with conservative claims only.

## Safety boundary

P83 is monitor-only and local/mock. It may recommend updating a communication draft or promoting a rollback draft for human review, but it never claims unattended production operation or performs external effects.
