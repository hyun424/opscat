# OpsCat Demo Walkthrough

This walkthrough is the intended portfolio demo path for the local mock MVP. It intentionally avoids real Sentry, GitHub, Slack, production mutation, and arbitrary shell execution.

## Current blocker behavior

Worker-5 verification against leader head `055ac28158b98cd757861041548ed35bfaac3073` shows the app currently fails to import because `app/models/action.py` has an indentation syntax error. Running `python scripts/demo.py` currently fails with:

```text
IndentationError: unexpected indent
```

Use this document as the expected walkthrough once that integration blocker is repaired.

## 1. Start local API

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","service":"opscat"}
```

## 2. Trigger mock alert

```bash
INCIDENT_JSON=$(curl -s -X POST http://localhost:8000/webhooks/alerts/mock \
  -H 'content-type: application/json' \
  -d '{"scenario":"payment_api_deploy_regression","environment":"staging","severity":"high","message":"Payment API timeout spike"}')

echo "$INCIDENT_JSON"
```

Expected behavior:

- An incident is created.
- Mock context evidence is attached.
- The deterministic agent recommends a remediation.
- The action is policy-classified as `REQUIRE_APPROVAL`.
- Incident status becomes `waiting_approval`.

## 3. Approve the mock action

```bash
export INCIDENT_JSON
ACTION_ID=$(python - <<'PY'
import json
import os
print(json.loads(os.environ["INCIDENT_JSON"])["actions"][0]["id"])
PY
)

APPROVAL_JSON=$(curl -s -X POST "http://localhost:8000/approvals/$ACTION_ID" \
  -H 'content-type: application/json' \
  -d '{"decision":"approve","actor":"demo-user","reason":"approve mock rollback PR draft"}')

echo "$APPROVAL_JSON"
```

Expected behavior:

- The approval is recorded.
- The mock action executes locally only.
- The incident transitions through execution/verification and ends as `resolved` when recovery checks pass.
- A markdown report path is returned.

## 4. Inspect report

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

Compare the shape to [`sample-incident-report.md`](sample-incident-report.md).

## 5. Simulate Night Autopilot

```bash
curl -s -X POST http://localhost:8000/night-autopilot/simulate \
  -H 'content-type: application/json' \
  -d '{}'
```

Expected behavior:

- Only low-risk allowlisted mock actions are eligible.
- Production mutation, shell execution, and high-risk actions remain denied or escalated.
- The response includes a morning-report style summary.

## 6. Verification gate

Before presenting the demo as green, run:

```bash
ruff check app tests scripts
mypy app tests scripts
python -m pytest
python scripts/demo.py
python -m compileall app tests scripts
docker compose config
```

All core checks should pass without generated artifacts being committed.
