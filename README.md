# OpsCat

OpsCat is a local **agentic AI on-call system** for human-on-exception operations. It receives a mock alert, builds incident state, gathers sanitized operational context with tools, produces evidence-backed hypotheses, proposes remediation, runs the action through deterministic policy/risk gates, requires approval for unsafe writes, executes only local/mock actions, verifies recovery, wakes humans only on exception, and writes an auditable incident report.

This repository is intended as a portfolio-grade Agentic AI Engineer artifact and paid-beta design seed: it emphasizes state, tools, tenant boundaries, policy, approvals, verification, wake-up contracts, auditability, privacy, and safety boundaries rather than chatbot-style prompting.

> Current status: the local/mock MVP is green through compile, lint, typecheck, pytest, deterministic demo, Docker Compose config, and coverage gates. It now includes asynchronous webhook queueing by default, immutable execution attempts, connector idempotency replay/conflict protection, and a server-rendered operator dashboard. See [`docs/integration-verification.md`](docs/integration-verification.md).

## Portfolio demo evidence

OpsCat is designed to be read as an agentic AI incident-response/operator-replacement portfolio project. It proves the shape of an operator loop: tool use, evidence-grounded reasoning, policy and safety gates, autonomous observe-to-report flow, evaluation/benchmarking, human approval handoff, and a local/mock-only dry-run boundary.

Run the one-command portfolio pack:

```bash
uv run --no-sync --extra dev python scripts/run_portfolio_demo_pack.py
```

Expected smoke line:

```text
walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0
```

Reviewer links:

- [`docs/portfolio-demo.md`](docs/portfolio-demo.md) — five-minute portfolio narrative and commands.
- [`docs/operator-walkthrough.md`](docs/operator-walkthrough.md) — operator walkthrough from observe to improve.
- [`docs/release-evidence.md`](docs/release-evidence.md) — release gates, evidence commands, and P93 proof.
- [`docs/architecture.md`](docs/architecture.md) — local/mock architecture and safety boundaries.

Boundary: the portfolio demo is local/mock-only. It performs no auth work, live APIs, credentials, network, production mutation, real remediation/action execution, or external model/API calls; it is not production autonomy.

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
- SQLAlchemy persistence for incidents, evidence, action proposals, approval decisions, execution attempts, workflow jobs, connector replay records, audit events, and timeline events.
- Deterministic mock agent; no LLM key is required for the demo path.
- Action registry with risk metadata, preconditions, approval requirements, allowed environments, and post-checks.
- Mock action execution for rollback PR draft, incident ticket, non-production worker restart, verification, and report generation.
- Recovery verification and markdown incident reports under `data/mock_reports/`.
- Docker Compose for FastAPI + PostgreSQL.
- Pytest coverage for state machine, policy, full mock alert flow, approval/rejection, workflow queueing, connector idempotency, operator dashboard scoping, and Night Autopilot.

## Documentation map

- [`docs/portfolio-summary.md`](docs/portfolio-summary.md) — recruiter-facing and paid-beta framing summary.
- [`docs/beta-walkthrough.md`](docs/beta-walkthrough.md) — 10-minute local beta walkthrough from connector preview to report.
- [`docs/connector-permissions.md`](docs/connector-permissions.md) — least-privilege connector permission preview.
- [`docs/release-evidence.md`](docs/release-evidence.md) — release gate, eval artifacts, and verification profiles.
- [`docs/portfolio-quality-bar.md`](docs/portfolio-quality-bar.md) — completion gates and quality contract.
- [`docs/architecture.md`](docs/architecture.md) — runtime architecture, control-plane/connector model, and data boundary.
- [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md) — demo script, API walkthrough, and current blocker behavior.
- [`docs/sample-incident-report.md`](docs/sample-incident-report.md) — representative incident report output.
- [`docs/integration-verification.md`](docs/integration-verification.md) — exact PASS/FAIL verification evidence.
- [`docs/deployment-dry-run.md`](docs/deployment-dry-run.md) — local Docker/Postgres deployment dry run and stable vs experimental boundary.
- [`CHANGELOG.md`](CHANGELOG.md) — versioned local/mock release evidence notes.
- [`.omx/plans/opscat-master-build-prompt.md`](.omx/plans/opscat-master-build-prompt.md) — original autonomous build contract.

## Open-source quickstart

A new contributor can run OpsCat locally without auth setup, cloud accounts, or production credentials. No auth setup is required for the P5 quickstart; auth is deferred; OpsCat uses the existing local-header demo identity in local/mock mode.

```bash
git clone <your-fork-or-repo-url>
cd opscat
cp .env.example .env
make install
make quickstart
```

Useful local commands:

```bash
make demo      # deterministic incident -> approval -> report demo
make evals     # golden incident evals plus connector safety evals
make test      # pytest regression suite
make verify    # full local release gate
make run       # start FastAPI on http://127.0.0.1:8000
```

Do not use production credentials, customer logs, or real provider tokens in the open-source quickstart. The demo path is local/mock-only and uses a local-header demo identity instead of production authentication.

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

Run the deterministic demo without external services:

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

## Operator dashboard

After creating incidents, open the local operator inbox:

```bash
open http://localhost:8000/operator
# or
curl -s http://localhost:8000/operator
```

The server-rendered dashboard is workspace-scoped, escapes incident content, and shows evidence, timeline, actions, execution attempts, and report links. Approval execution remains JSON API-based (`POST /approvals/{action_id}`) rather than unsafe HTML form posts.

## Manual API walkthrough

Start the API first:

```bash
uvicorn app.main:app --reload
```

Create a mock incident:

```bash
INCIDENT_JSON=$(curl -s -X POST 'http://localhost:8000/webhooks/alerts/mock?process_now=true' \
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

## Golden evals

OpsCat includes deterministic local eval evidence for operator-replacement trust. The reviewer-facing evidence pack is [`docs/eval-report.md`](docs/eval-report.md).

Run incident golden evals:

```bash
python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md
```

Run Connector evals:

```bash
python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md
```

The current P4 corpus covers 23 incident scenarios across bad deploys, external dependency failures, worker backlog, duplicate/stale alerts, low-confidence ambiguity, missing runbooks, protected auth/security/data domains, verification failure, prompt-injection-like logs, and secret-bearing alerts. Connector evals add 7 fake/local safety scenarios covering missing credentials, provider timeouts, malformed results, read-only contract violations, idempotency replay, and idempotency conflict handling. Both reports are intentionally local/mock-only and are included in `bash scripts/verify.sh`.

## Verification commands

Run the full local release gate before claiming a build is ready:

```bash
bash scripts/verify.sh
```

Run local database migrations explicitly when preparing a database outside app startup:

```bash
python scripts/migrate.py upgrade
python scripts/migrate.py status
```

The gate runs compileall, Ruff, mypy, pytest, a stdlib coverage gate, the golden eval runner, local demo smoke, Docker Compose config validation, tracked generated artifact scan, and whitespace diff checks.

Latest verification evidence is in [`docs/integration-verification.md`](docs/integration-verification.md). The default webhook path returns `202 Accepted` and queues work; use `?process_now=true` for copy-paste synchronous demos.

## Documentation

- [Contributor Guide](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md)
- [Local API Guide](docs/api.md)
- [Examples](examples/README.md)
- [AI Development Team](docs/operations/ai-development-team.md)
- [Production AI Team Plan](docs/operations/production-ai-team-plan.md)
- [P5 OSS/Productization Ticket Roadmap](docs/operations/p5-ticket-roadmap.md)

## P6 agentic loop demo

OpsCat now includes a local/mock seven-stage agentic operations loop: observe → correlate → diagnose → plan → risk → act → verify. Run it without external credentials:

```bash
uv run --no-sync --extra dev python scripts/demo_agentic_loop.py
```

Evidence and docs: `docs/agentic-loop.md`, `docs/portfolio-demo.md`, `docs/security-review-p6.md`, and `docs/release-evidence.md`. This remains a local/beta portfolio demo and does not claim unattended production mutation safety.
