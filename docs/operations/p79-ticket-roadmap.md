# P79 Action Sandbox Hardening Roadmap

P79 hardens proposed action routing before any action can leave local/mock evaluation. The sandbox evaluates allowlists, blast radius, reversibility, approval state, dry-run capability, credential/network boundaries, production mutation boundaries, and shell boundaries, then returns allow, approval-required, mock-only, or block decisions.

## Tickets

- P79-001: Define local/mock proposed-action fixture cases.
- P79-002: Parse proposed actions without live API calls, credentials, networks, shell execution, production mutation, or action execution.
- P79-003: Evaluate allowlist and prohibited-action boundaries.
- P79-004: Evaluate blast radius, reversibility, and dry-run capability.
- P79-005: Evaluate approval state and route bounded mutations to human approval.
- P79-006: Block credential, network, shell, production-mutation, and unbounded proposals.
- P79-007: Add CLI JSON/Markdown sandbox reporting.
- P79-008: Wire P79 into release evidence and verification profiles.

## Boundary

P79 is offline local/mock evaluation only. It does not execute actions, execute shell commands, call live APIs, read credentials, call networks, mutate production, perform remediation, or claim unattended production operation.
