# OpsCat

OpsCat is a local AI on-call / agentic operations automation MVP. It receives mock alerts, gathers sanitized mock observability, deploy, runbook, and prior-incident context, generates deterministic evidence-backed hypotheses, proposes safe remediation, enforces policy/risk checks, supports approval/rejection, executes mock actions, verifies recovery, and writes an auditable incident report.

This MVP intentionally uses **mock Sentry/GitHub/Slack-style tools only**. There is no real Sentry, GitHub, or Slack integration yet; no production rollback; no database mutation tool; and no arbitrary shell execution tool.

## What the local MVP is expected to include

- FastAPI API with `/health`, mock alert ingestion, incident reads, approval API, reports, and Night Autopilot simulation.
- SQLAlchemy persistence for incidents, evidence, action proposals, approval decisions, and timeline events.
- Deterministic mock agent; no LLM key is required for the demo path.
- Action registry with risk metadata, preconditions, approval requirements, allowed environments, and post-checks.
- Policy engine decisions: `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, `ESCALATE`.
- Mock action execution for rollback PR draft, incident ticket, non-production worker restart, verification, and report generation.
- Recovery verification and markdown incident reports under `data/mock_reports/`.
- Docker Compose for FastAPI + PostgreSQL.
- Pytest coverage for state machine, policy, full mock alert flow, approval/rejection, and Night Autopilot.

See also:

- [`docs/architecture.md`](docs/architecture.md) for the intended module boundaries and data flow.
- [`docs/integration-verification.md`](docs/integration-verification.md) for the current worker-5 smoke-check results and blockers.
- `.omx/plans/opscat-master-build-prompt.md` for the original build contract.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the API with SQLite fallback:

```bash
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

Run with PostgreSQL via Docker Compose:

```bash
docker compose up --build
curl http://localhost:8000/health
```

## Deterministic README demo

Run the deterministic in-process demo without external services:

```bash
python scripts/demo.py
```

Expected output includes:

- `Health: {'status': 'ok', 'service': 'opscat'}`
- an incident initially in `waiting_approval`
- a `mock.create_rollback_pr` proposal requiring approval
- final incident status `resolved`
- a generated report path
- one Night Autopilot simulated action

## Manual API flow

Start the API first:

```bash
uvicorn app.main:app --reload
```

Create a mock incident:

```bash
INCIDENT_JSON=$(curl -s -X POST http://localhost:8000/webhooks/alerts/mock \
  -H 'content-type: application/json' \
  -d '{"scenario":"payment_api_deploy_regression","environment":"staging","severity":"high","message":"Payment API timeout spike"}')

echo "$INCIDENT_JSON"
```

Extract the first proposed action ID. Exporting the shell variable is required because the Python snippet reads from `os.environ`:

```bash
export INCIDENT_JSON
ACTION_ID=$(python - <<'PY'
import json
import os
print(json.loads(os.environ["INCIDENT_JSON"])["actions"][0]["id"])
PY
)

echo "$ACTION_ID"
```

Approve the mock action:

```bash
APPROVAL_JSON=$(curl -s -X POST "http://localhost:8000/approvals/$ACTION_ID" \
  -H 'content-type: application/json' \
  -d '{"decision":"approve","actor":"demo-user","reason":"approve mock action"}')

echo "$APPROVAL_JSON"
```

Generate or fetch the report for the incident:

```bash
export APPROVAL_JSON
INCIDENT_ID=$(python - <<'PY'
import json
import os
print(json.loads(os.environ["APPROVAL_JSON"])["incident"]["id"])
PY
)

curl -s "http://localhost:8000/incidents/$INCIDENT_ID/report"
```

Simulate Night Autopilot:

```bash
curl -s -X POST http://localhost:8000/night-autopilot/simulate \
  -H 'content-type: application/json' \
  -d '{}'
```

## Verification commands

Run these before claiming an integrated MVP build is complete:

```bash
ruff check app tests scripts
mypy app tests scripts
python -m pytest
python scripts/demo.py
python -m compileall app tests scripts
docker compose config
```

Worker-5's integration smoke on **2026-07-06 UTC** found blockers in the latest inspected integrated head; see [`docs/integration-verification.md`](docs/integration-verification.md). Do not call the full demo verified until those failures are fixed and the commands above pass.

## Safety boundaries

- Read-only context gathering is automatic.
- Mock rollback PR and incident-ticket writes require approval in Smart Approval Mode.
- Night Autopilot can only run allowlisted low-risk mock actions in covered services/environments.
- Prohibited actions such as arbitrary shell execution, database mutation, cloud deletion, secret access, and production mutation are denied by policy.
- Evidence stores sanitized snippets and metadata, not wholesale raw logs.
