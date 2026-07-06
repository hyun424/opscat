# OpsCat Threat Model

## Assets
- Incident data and evidence snippets.
- Integration tokens and credentials.
- Action approval records.
- Customer service topology and runbooks.
- Agent prompts, tool outputs, and audit logs.

## Primary Risks
1. Agent executes an unsafe action.
2. Cross-tenant data leak.
3. Secret or PII leakage into LLM input or reports.
4. Compromised integration token performs unauthorized changes.
5. Prompt injection from logs/runbooks influences tool execution.
6. Duplicate webhook causes repeated action execution.
7. Night Autopilot performs a bad remediation while humans sleep.

## Mitigations
- Deterministic policy engine gates every action.
- Capability grants are scoped by tenant, service, environment, and action.
- Dangerous actions are denied by default.
- Redaction runs before model input and report generation.
- Tool execution uses typed action registry, not arbitrary shell.
- Approval records and action states prevent hidden mutation.
- Post-checks and max-attempt limits bound Night Autopilot.
- Self-hosted connector keeps raw logs inside customer infrastructure.

## MVP Security Boundaries
The MVP is local/mock-only. It must not claim real production safety until authentication, tenant isolation, encrypted secrets, and connector deployment are implemented.
