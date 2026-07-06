# OpsCat Portfolio Quality Bar

OpsCat should be good enough to place at the top of an Agentic AI Engineer portfolio. Do not stop at a toy MVP.

## Required Portfolio Story
OpsCat demonstrates an agentic AI operations system that:

1. Receives an incident alert.
2. Builds incident state and timeline.
3. Uses tools to gather context.
4. Produces evidence-backed hypotheses.
5. Proposes a remediation action.
6. Runs action through deterministic policy/risk gates.
7. Requires approval for unsafe writes.
8. Executes only local/mock safe actions.
9. Verifies recovery.
10. Generates an auditable report.

## Non-Negotiable Completion Gates

### Functionality
- Mock alert to incident flow works end-to-end.
- Investigation returns structured hypotheses and evidence.
- Policy engine distinguishes ALLOW / REQUIRE_APPROVAL / DENY / ESCALATE.
- Dangerous actions are denied by test.
- Approval-gated mock actions execute only after approval.
- Verify and report endpoints/services work.
- Night Autopilot simulation works or is explicitly documented as partial with tests.

### Safety
- No arbitrary shell execution product surface.
- No real production mutation.
- No real Sentry/GitHub/Slack side effects in MVP.
- No secret/PII logging in prompts or sample evidence.
- All actions have risk metadata and post-checks.

### Engineering Quality
- No generated artifacts committed: __pycache__, .pyc, egg-info, pytest/ruff cache.
- `ruff` passes.
- `pytest` passes without skipped core MVP tests.
- `py_compile` or `compileall` passes.
- Type check passes where configured, or gaps are documented.
- Docker Compose config validates.
- README demo commands are copy-paste runnable.

### Documentation
- README explains product thesis, architecture, setup, demo, API examples, and safety model.
- Architecture doc explains control plane / connector model and data boundary.
- Integration verification doc shows exact PASS/FAIL evidence.
- Include a sample incident report output.
- Include a recruiter-facing portfolio summary.

### Evaluation
- At least four golden incident scenarios exist:
  - bad deploy
  - external API timeout
  - worker queue backlog
  - false positive / duplicate alert storm
- Each scenario includes expected cause, expected evidence, expected action, expected policy decision.
- Evaluation can run locally without external credentials.

## Shutdown Rule
Do not shut down the team until:
- all tasks are completed or explicitly superseded,
- repo hygiene is clean,
- tests and demo are green,
- docs reflect actual current behavior,
- remaining gaps are explicit and acceptable for a portfolio MVP.
