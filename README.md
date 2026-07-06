# OpsCat

OpsCat is a local **agentic AI on-call system** for human-on-exception operations. It receives a mock alert, builds incident state, gathers sanitized operational context with tools, produces evidence-backed hypotheses, proposes remediation, runs the action through deterministic policy/risk gates, requires approval for unsafe writes, executes only local/mock actions, verifies recovery, wakes humans only on exception, and writes an auditable incident report.

This repository is intended as a portfolio-grade Agentic AI Engineer artifact and paid-beta design seed: it emphasizes state, tools, tenant boundaries, policy, approvals, verification, wake-up contracts, auditability, privacy, and safety boundaries rather than chatbot-style prompting.

> Current status: the docs and design contract are portfolio-ready, but the latest inspected integrated code is not yet green. Worker-5 verification on current leader head `055ac28158b98cd757861041548ed35bfaac3073` found a syntax blocker in `app/models/action.py`; see [`docs/integration-verification.md`](docs/integration-verification.md). The README demo flow below is the intended copy-paste path once that blocker is fixed.

## Portfolio story

OpsCat demonstrates a production-minded agent loop:

1. Observe a Sentry-like mock alert.
2. Persist incident state and timeline.
3. Gather context through mock read-only tools.
4. Generate structured hypotheses with evidence IDs.
5. Propose a remediation action with preconditions and post-checks.
6. Classify action risk and evaluate policy.
7. Require approval for risky writes.
8. Execute only local/mock safe actions.
9. Verify recovery.
10. Generate an auditable markdown report.


## Human-on-exception promise

OpsCat is meant to replace continuous human monitoring, not human accountability. Routine known incidents should be classified, investigated, safely acted on, verified, and reported automatically. Humans are woken when the incident is high-risk, low-confidence, protected-domain, policy-denied, unverified, or exceeds bounded retry limits.

See [`docs/human-on-exception-operations.md`](docs/human-on-exception-operations.md) and [`docs/wake-up-report.md`](docs/wake-up-report.md).

## Paid-beta readiness stance

The MVP remains local/mock-only. It is not production-ready until authentication, tenant-scoped authorization, encrypted integration token storage, real connector deployment, and redaction/idempotency tests exist. The paid-beta readiness bar and threat model are explicit in [`docs/paid-beta-readiness.md`](docs/paid-beta-readiness.md) and [`docs/threat-model.md`](docs/threat-model.md).

## Safety boundary

This MVP intentionally uses **mock Sentry/GitHub/Slack-style tools only**.

It does **not** include:

- real Sentry, GitHub, or Slack side effects;
- production rollback;
- Kubernetes/cloud mutation;
- database mutation actions;
- arbitrary shell execution as a product tool;
- secret or PII collection in sample evidence.

Safety is enforced by explicit action metadata, risk classification, approval state, and policy decisions: `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, and `ESCALATE`.

## Included surfaces

- FastAPI API with `/health`, mock alert ingestion, incident reads, approval API, reports, and Night Autopilot simulation.
- SQLAlchemy persistence for incidents, evidence, action proposals, approval decisions, and timeline events.
- Deterministic mock agent; no LLM key is required for the demo path.
- Action registry with risk metadata, preconditions, approval requirements, allowed environments, and post-checks.
- Mock action execution for rollback PR draft, incident ticket, non-production worker restart, verification, and report generation.
- Recovery verification and markdown incident reports under `data/mock_reports/`.
- Docker Compose for FastAPI + PostgreSQL.
- Pytest coverage for state machine, policy, full mock alert flow, approval/rejection, and Night Autopilot once integration blockers are repaired.

## Documentation map

- [`docs/portfolio-summary.md`](docs/portfolio-summary.md) — recruiter-facing and paid-beta framing summary.
- [`docs/portfolio-quality-bar.md`](docs/portfolio-quality-bar.md) — completion gates and quality contract.
- [`docs/architecture.md`](docs/architecture.md) — runtime architecture, control-plane/connector model, and data boundary.
- [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md) — demo script, API walkthrough, and current blocker behavior.
- [`docs/sample-incident-report.md`](docs/sample-incident-report.md) — representative incident report output.
- [`docs/integration-verification.md`](docs/integration-verification.md) — exact PASS/FAIL verification evidence.
- [`.omx/plans/opscat-master-build-prompt.md`](.omx/plans/opscat-master-build-prompt.md) — original autonomous build contract.

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

## Deterministic in-process demo

Once the current syntax blocker is repaired, run the deterministic demo without external services:

```bash
python scripts/demo.py
```

Expected output shape:

```text
Health: {'status': 'ok', 'service': 'opscat'}
Incident: <incident-id> initial_status= waiting_approval
Action: mock.create_rollback_pr REQUIRE_APPROVAL
Final status: resolved
Report path: data/mock_reports/incident-<incident-id>.md
Night Autopilot actions: 1
```

## Manual API walkthrough

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

Run the full local release gate before claiming a build is ready:

```bash
bash scripts/verify.sh
```

The gate runs compileall, Ruff, mypy, pytest, a stdlib coverage gate, local demo smoke, Docker Compose config validation, tracked generated artifact scan, and whitespace diff checks.

Current worker-5 evidence is in [`docs/integration-verification.md`](docs/integration-verification.md). Do not claim the full demo is verified until all core checks are green.

## Documentation

- [AI Development Team](docs/operations/ai-development-team.md)
- [Production AI Team Plan](docs/operations/production-ai-team-plan.md)
