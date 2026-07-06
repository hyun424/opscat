# OpsCat

OpsCat is a local AI on-call / agentic operations automation MVP. It receives mock alerts, gathers sanitized mock observability/deploy/runbook context, generates deterministic evidence-backed hypotheses, proposes safe remediation, enforces policy/risk checks, supports approval/rejection, executes mock actions, verifies recovery, and writes an auditable incident report.

This MVP intentionally uses **mock Sentry/GitHub/Slack-style tools only**. There is no real external integration, no production rollback, no database mutation tool, and no arbitrary shell execution tool.

## What is included

- FastAPI API with `/health`, mock alert ingestion, incident reads, approval API, reports, and Night Autopilot simulation.
- SQLAlchemy persistence for incidents, evidence, action proposals, approval decisions, and timeline events.
- Deterministic mock agent; no LLM key is required.
- Action registry with risk metadata, preconditions, approval requirements, allowed environments, and post-checks.
- Policy engine decisions: `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, `ESCALATE`.
- Mock action execution for rollback PR draft, incident ticket, and non-production worker restart.
- Recovery verification and markdown incident reports under `data/mock_reports/`.
- Docker Compose for FastAPI + PostgreSQL.
- Pytest coverage for state machine, policy, full mock alert flow, approval/rejection, and Night Autopilot.

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

## README demo (verified)

Run the deterministic demo without external services:

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

Manual API flow:

```bash
INCIDENT_JSON=$(curl -s -X POST http://localhost:8000/webhooks/alerts/mock \
  -H 'content-type: application/json' \
  -d '{"scenario":"payment_api_deploy_regression","environment":"staging","severity":"high","message":"Payment API timeout spike"}')

echo "$INCIDENT_JSON"
ACTION_ID=$(python - <<'PY'
import json, os
print(json.loads(os.environ['INCIDENT_JSON'])['actions'][0]['id'])
PY
)

curl -s -X POST "http://localhost:8000/approvals/$ACTION_ID" \
  -H 'content-type: application/json' \
  -d '{"decision":"approve","actor":"demo-user","reason":"approve mock action"}'
```

Night Autopilot simulation:

```bash
curl -s -X POST http://localhost:8000/night-autopilot/simulate \
  -H 'content-type: application/json' \
  -d '{}'
```

## Verification commands

```bash
ruff check app tests scripts
mypy app tests scripts
python -m pytest
python scripts/demo.py
python -m compileall app tests scripts
```

## Safety boundaries

- Read-only context gathering is automatic.
- Mock rollback PR and incident-ticket writes require approval in Smart Approval Mode.
- Night Autopilot can only run allowlisted low-risk mock actions in covered services/environments.
- Prohibited actions such as arbitrary shell execution, DB mutation, cloud deletion, secret access, and production mutation are denied by policy.
- Evidence stores sanitized snippets and metadata, not wholesale raw logs.
