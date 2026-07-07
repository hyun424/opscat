# OpsCat P6 Safety Policy

Policy decisions expose a P6 route model:

- `auto_execute` — read-only/report/timeline actions that policy allows now;
- `approval_required` — reversible local/mock write actions that require human approval;
- `human_required` — unknown or ambiguous actions that need an operator;
- `blocked` — prohibited actions such as production rollback, arbitrary shell, database mutation, cloud deletion, or secret access.

Inputs include environment, blast radius, reversibility, data-loss/secret risk, action type, confidence/evidence, night-autopilot mode, and prior failures. Unsafe or production-like mutations fail closed even if an agent plan recommends them.
