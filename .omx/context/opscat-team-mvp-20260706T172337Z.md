# OpsCat Team MVP Context

## Task Statement
Build OpsCat MVP using `.omx/plans/opscat-master-build-prompt.md` as the execution contract.

## Desired Outcome
A local FastAPI/Postgres MVP where a mock alert creates an incident, the agent gathers mock context, produces evidence-backed hypotheses, applies policy/risk checks, supports approval/rejection, executes mock actions, verifies recovery, and generates a report.

## Known Facts / Evidence
- Project root: `/Users/gimdonghyeon/projects/opscat`
- Existing plan files:
  - `.omx/plans/opscat-mvp-plan.md`
  - `.omx/plans/opscat-product-decisions.md`
  - `.omx/plans/opscat-master-build-prompt.md`
- Product direction: web control plane + customer-side agent later; local Docker mock MVP first.
- Default mode: Smart Approval Mode.
- Night Autopilot should be simulated in MVP.

## Constraints
- Do not integrate real Sentry/GitHub/Slack first.
- Do not implement dangerous production mutation.
- No raw log bulk ingestion.
- All action proposals need risk metadata and post-checks.
- Tests and README demo are required before completion.

## Unknowns / Open Questions
- Final UI can wait; API + README demo is sufficient for MVP.
- LLM integration should be abstracted; deterministic mock agent is acceptable initially.

## Likely Touchpoints
- FastAPI app scaffold
- SQLModel/SQLAlchemy models
- Incident state machine
- Tool registry
- Mock scenarios
- Policy/risk engine
- Approval API
- Verification/report services
- Pytest suite
