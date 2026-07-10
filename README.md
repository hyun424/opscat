# OpsCat

OpsCat is a local **agentic AI on-call system** for human-on-exception operations. It receives a mock alert, builds incident state, gathers sanitized operational context with tools, produces evidence-backed hypotheses, proposes remediation, runs the action through deterministic policy/risk gates, requires approval for unsafe writes, executes only local/mock actions, verifies recovery, wakes humans only on exception, and writes an auditable incident report.

This repository is intended as a portfolio-grade Agentic AI Engineer artifact and paid-beta design seed: it emphasizes state, tools, tenant boundaries, policy, approvals, verification, wake-up contracts, auditability, privacy, and safety boundaries rather than chatbot-style prompting.

> Current status: the local/mock MVP is green through compile, lint, typecheck, pytest, deterministic demo, Docker Compose config, and coverage gates. P96 adds an opt-in Prometheus read-only connector while fixture mode remains the default; P97-P100 add causal, broad, and stateful evaluation; P101 adds executed read-only tool selection before evidence-gated action; P102 evaluates a fail-closed LLM tool planner under language/topology/injection perturbations. No production actions are enabled. See [`docs/integration-verification.md`](docs/integration-verification.md).

## Portfolio demo evidence

OpsCat is designed to be read as an agentic AI incident-response/operator-replacement portfolio project. It proves the shape of an operator loop: tool use, evidence-grounded reasoning, policy and safety gates, autonomous observe-to-report flow, evaluation/benchmarking, human approval handoff, and a local/mock-only dry-run boundary.

Run the one-command portfolio pack:

```bash
uv run --no-sync --extra dev python scripts/run_portfolio_demo_pack.py
```

For the fastest reviewer-facing operator transcript, run:

```bash
uv run --no-sync --extra dev python scripts/run_operator_transcript_demo.py
```

Expected smoke line:

```text
walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0
scenarios=4 transcript_steps>=40 hypotheses>=12 executions=0 recovery_proven=1 blocked=2 human_gated=1
```

Reviewer links:

- [`docs/portfolio-demo.md`](docs/portfolio-demo.md) — five-minute portfolio narrative and commands.
- [`docs/operator-transcript-demo.md`](docs/operator-transcript-demo.md) — best quick transcript demo for reviewers.
- [`docs/operator-walkthrough.md`](docs/operator-walkthrough.md) — operator walkthrough from observe to improve.
- [`docs/release-evidence.md`](docs/release-evidence.md) — release gates, evidence commands, P93/P94 demo proof, P95 clean-clone proof, P96 Prometheus shadow connector, and P97 causal remediation benchmark.
- [`docs/operations/p98-final-summary.md`](docs/operations/p98-final-summary.md) — selector comparison, blind causal metrics, and LLM safety boundary.
- [`docs/operations/p99-final-summary.md`](docs/operations/p99-final-summary.md) — comprehensive operational failure taxonomy and broad causal results.
- [`docs/operations/p100-final-summary.md`](docs/operations/p100-final-summary.md) — stateful multi-step benchmark, blind-split lift, and safety results.
- [`docs/operations/p101-final-summary.md`](docs/operations/p101-final-summary.md) — hidden-evidence tool selection, recovery retention, and safety results.
- [`docs/operations/p102-final-summary.md`](docs/operations/p102-final-summary.md) — offline and NVIDIA LLM tool-planning robustness evidence.
- [`docs/architecture.md`](docs/architecture.md) — local/mock architecture and safety boundaries.

Boundary: the portfolio demo is local/mock-only. It performs no auth work, live APIs, credentials, network, production mutation, real remediation/action execution, or external model/API calls; it is not production autonomy.

## Causal remediation evaluation (P97)

P97 measures outcomes instead of awarding points for a fixture answer. It replays the same deterministic fault state through `no_action`, `human_runbook`, and `opscat`, samples a real ephemeral `127.0.0.1` HTTP workload before and after intervention, and compares recovery, utility, durability, collateral effects, and escalation behavior. The selector receives visible evidence only; family/variant/split labels, scorer-only required actions, and harmful-action maps stay outside its input. Non-`act` decisions cannot mutate lab state.

Run the bounded 12-case smoke:

```bash
uv run --no-sync --extra dev python scripts/run_causal_remediation_benchmark.py \
  --output-json /tmp/opscat-p97-smoke.json \
  --output-md /tmp/opscat-p97-smoke.md
```

Run all 120 cases across three seeds and three intervention arms:

```bash
uv run --no-sync --extra dev python scripts/run_causal_remediation_benchmark.py \
  --full-matrix \
  --output-json /tmp/opscat-p97-full.json \
  --output-md /tmp/opscat-p97-full.md
```

The recorded full matrix produced 1,080 trials and 64,800 loopback HTTP requests. OpsCat recovered 44.17% versus 16.67% for no-action and 90.0% for the curated human runbook after the P100 catalog-consistency correction, yielding a 0.275 causal recovery lift over no-action while all hard safety counters remained zero. This is synthetic-lab comparative evidence, not proof of production remediation effectiveness.

## Selector comparison (P98)

Compare the deterministic selector, an observation-only ablation, and the local LLM-shaped selector:

```bash
uv run --no-sync --extra dev python scripts/run_selector_comparison.py \
  --full-matrix --output-json /tmp/opscat-p98-full.json
```

The default run is local and network-free. NVIDIA is explicit opt-in with `--include-nvidia` and `NVIDIA_API_KEY`; the model can propose a bounded decision but cannot execute actions. P98 currently measures the same 44.17% overall and 12.50% blind recovery for the rule and mock LLM baselines, with 0% harmful actions and a passed hard safety gate. This is a comparison harness, not production effectiveness or operator-replacement approval.

## Comprehensive operational matrix (P99)

Run a bounded, family-spread smoke:

```bash
uv run --no-sync --extra dev python scripts/run_operational_scenario_matrix.py \
  --max-cases 20 --sample-size 5 \
  --output-json /tmp/opscat-p99-smoke.json \
  --output-md /tmp/opscat-p99-smoke.md
```

Run all 52 families and 520 cases across three deterministic seeds:

```bash
uv run --no-sync --extra dev python scripts/run_operational_scenario_matrix.py \
  --full-matrix --sample-size 10 \
  --output-json /tmp/opscat-p99-full.json \
  --output-md /tmp/opscat-p99-full.md
```

The recorded full matrix ran 4,680 arms and 140,400 loopback HTTP observations. OpsCat recovered 34.55%, the curated human runbook recovered 89.87% after the P100 catalog-consistency correction, and no-action recovered 11.47%. Escalation correctness and precision were both 100%, harmful actions were 0%, and every hard safety gate passed. The taxonomy is broad but not literally exhaustive, and the result is synthetic-lab evidence only.

## Stateful multi-step investigator (P100)

Run all 520 cases across three seeds and four equal-state arms:

```bash
uv run --no-sync --extra dev python scripts/run_stateful_incident_investigator.py \
  --seeds 11,29,47 --sample-size 10 --max-steps 3 \
  --output-json /tmp/opscat-p100-full.json \
  --output-md /tmp/opscat-p100-full.md
```

The recorded full matrix ran 6,240 trials and 183,990 loopback HTTP requests. The stateful agent recovered 56.47% overall versus 34.55% for the same one-shot selector and improved blind recovery from 2.88% to 39.42%. It recorded zero collateral regressions, 100% expected-escalation recall/precision, and passed every hard safety gate. The remaining gap to the 89.87% curated human runbook and the synthetic-lab boundary remain explicit.

## Tool-using hypothesis investigator (P101)

```bash
uv run --no-sync --extra dev python scripts/run_tool_investigation_benchmark.py \
  --seeds 11,29,47 --sample-size 10 \
  --output-json /tmp/opscat-p101-full.json \
  --output-md /tmp/opscat-p101-full.md
```

P101 hides initial evidence and requires an executed read-only diagnostic before action. Across 4,680 trials it discovered the relevant tool in 100% of eligible arms, achieved 94.23% Top-1 tool accuracy, retained 100% of the direct-visible 56.54% recovery rate, and reduced a fixed-tool ablation to 1.35%. All tools and actions remain synthetic local boundaries.

## LLM diagnostic tool planner evaluation (P102)

```bash
uv run --no-sync --extra dev python scripts/run_llm_tool_planner_evaluation.py \
  --max-cases 52 --output-json /tmp/opscat-p102-mock.json

# Explicit live-provider evaluation; still advisory-only and executes no tool/action.
uv run --no-sync --extra dev python scripts/run_llm_tool_planner_evaluation.py \
  --max-cases 12 --include-nvidia --output-json /tmp/opscat-p102-nvidia.json
```

P102 tests one closed-registry diagnostic choice against original, paraphrased,
opaque-topology, and prompt-injection-like symptoms. The default fixture mode is
deterministic and network-free; NVIDIA mode is explicit opt-in, validates an exact
JSON contract, and fails closed before any tool or remediation execution.

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

The core MVP remains local/mock-first, with one explicit opt-in Prometheus read-only shadow path. It is not production-ready until authentication, tenant-scoped authorization, encrypted integration token storage, supervised real connector deployment, and broader live safety tests exist. The paid-beta readiness bar and threat model are explicit in [`docs/paid-beta-readiness.md`](docs/paid-beta-readiness.md) and [`docs/threat-model.md`](docs/threat-model.md).

## Safety boundary

This MVP uses **mock Sentry/GitHub/Slack-style tools by default** and exposes one explicit opt-in Prometheus read-only shadow connector.

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

## Prometheus read-only shadow probe

The default probe is an offline fixture and makes no network calls:

```bash
uv run --no-sync --extra dev python scripts/probe_prometheus.py
```

To inspect a real local or staging Prometheus endpoint, configure the trusted endpoint and exact hostname allowlist in `.env`:

```bash
OPSCAT_PROMETHEUS_BASE_URL=http://127.0.0.1:9090
OPSCAT_PROMETHEUS_ALLOWED_HOSTS=127.0.0.1
```

Then opt into the real read explicitly:

```bash
uv run --no-sync --extra dev python scripts/probe_prometheus.py \
  --mode real \
  --capability query.instant \
  --query up \
  --output-json /tmp/opscat-prometheus-probe.json
```

The connector does not accept request-controlled endpoint URLs. It uses GET only, blocks non-allowlisted hosts, requires HTTPS outside loopback, bounds query/response size, redacts provider output, and does not perform remediation.

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

Clean-clone reproducibility: P95 verified the private GitHub repository from a fresh `/private/tmp` clone at commit `c5a187d7ef2b13e9ada0b336b8bdf6d38ed700e3`. The cloned tree had no `.env`, `.DS_Store`, `.venv`, or `opscat.db` before setup, then passed `cp .env.example .env`, `make install`, `make quickstart`, and `bash scripts/verify.sh --profile full` with coverage `80.71% >= 60.00%`.

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
