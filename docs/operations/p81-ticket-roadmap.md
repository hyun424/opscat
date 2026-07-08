# P81 Rollback PR Draft Automation Roadmap

P81 converts local/mock P80 approval decisions into structured rollback PR draft artifacts. It is a safe operator handoff step: the artifact describes a proposed rollback PR, risk, evidence, human approval, verification, rollback/abort plan, and audit metadata without opening a real PR or executing rollback work.

## Tickets

- P81-001: Define fixture scenarios for safe config rollback, deploy revert, migration rollback, credential/auth rollback, and insufficient evidence.
- P81-002: Parse P80-shaped approval decisions without live GitHub API calls, credentials, networks, branch creation, git push, shell execution, production mutation, or action execution.
- P81-003: Generate structured draft artifacts with title, summary, proposed file changes or command-plan text, risk, evidence references, required approval, verification checklist, rollback/abort plan, and audit metadata.
- P81-004: Downgrade P80 auto-approval to draft-only unless external execution is explicitly configured.
- P81-005: Keep deploy rollback mock-only as draft-ready text requiring release manager review.
- P81-006: Require human review for migration/schema rollback drafts.
- P81-007: Block credential/auth rollback and reject insufficient-evidence drafts.
- P81-008: Add CLI JSON/Markdown reporting and wire P81 into release evidence and verification profiles.

## Boundary

P81 is offline local/mock draft generation only. It does not call live GitHub APIs, create branches, push commits, read credentials, call networks, mutate production, execute shell commands, run rollback commands, perform remediation, or claim unattended production operation. Every draft requires human approval before any external PR or rollback action.
