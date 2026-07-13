# OpsCat

OpsCat is an open-source **agentic incident-response laboratory** for human-on-exception operations. It receives fixture or explicitly enabled read-only telemetry, builds incident state, gathers sanitized evidence with bounded tools, produces evidence-backed hypotheses, proposes remediation, runs the proposal through deterministic policy/risk gates, executes only registered disposable local/mock/sandbox actions, verifies outcomes, and writes an auditable replay record.

This repository is intended as a portfolio-grade Agentic AI Engineer artifact and open-source research/development seed for **agentic AI incident-response/operator-replacement** research. It emphasizes state, tools, policy, approvals, verification, evaluation, auditability, privacy, and safety boundaries rather than chatbot-style prompting; the phrase describes the research target, not a production-readiness claim.

> **Public limitation:** OpsCat applies production-grade packaging and evidence practices, but its autonomous behavior is qualified only in deterministic local/mock/sandbox environments. Auth remains deferred. Production/staging mutations, credentialed execution, live connector writes, and operator-replacement claims are prohibited.

## Install and local demo

Supported: Python 3.12+ on macOS and Linux. The default demo is network-free and requires no secrets.

```bash
uv sync --frozen --extra dev
uv run --no-sync opscat demo --output /tmp/opscat-demo-replay.json
uv run --no-sync opscat contracts
```

See [`docs/install.md`](docs/install.md), [`docs/quickstart.md`](docs/quickstart.md), [`docs/public-contracts.md`](docs/public-contracts.md), and [`docs/limitations.md`](docs/limitations.md).

> Current status: the local/mock MVP is green through compile, lint, typecheck, pytest, deterministic demo, Docker Compose config, and coverage gates. P96 adds an opt-in Prometheus read-only connector while fixture mode remains the default; P97-P100 add causal, broad, and stateful evaluation; P101 adds executed read-only tool selection before evidence-gated action; P102 evaluates a fail-closed LLM tool planner; P103 adds negative-result replanning and measured multi-step recovery; P104 adds network-free evidence-gap sufficiency checks before policy handoff; P105 adds a local calibrated failure-forecasting harness with strict release-qualified prerequisites; P106 is simulation-only preventive planning with `p107_unlocked=false`; P107 adds a local/mock or isolated canary executor; P108 adds deterministic offline outcome learning and unapplied recommendations; P109 imports real public telemetry. On the frozen 25-case RCAEval blind split, P111 improves the paired P110 baseline from 68% to 80% service Top-1 and from 40% to 84% fault accuracy while preserving 100% evidence validity and zero unsafe-action counters. Release remains fail-closed because the 84% Top-1 target, loss-fault floor, and cryptographic reviewer gate were not met. No production actions are enabled. See [`docs/operations/p111-final-summary.md`](docs/operations/p111-final-summary.md).

## Supervised always-on local monitor and dead-man outbox (P131-P133)

P131 adds an independent foreground process that continuously tails local JSONL
telemetry, keeps an atomic tamper-evident cursor, resumes without accepting the
same observation twice, runs a synthetic serialization/detection/no-action canary,
and exposes separate heartbeat and readiness checks. It has no credentials,
network calls, subprocesses, or action execution authority. P132 adds graceful
SIGTERM/SIGINT receipts, bounded report retention, storage-pressure fail-closed
behavior, real-process crash/restart and lease-conflict qualification, and
validated systemd, launchd, and Compose examples.
P133 adds a separate credential-free process that converts only the independent
watchdog's closed health outcomes into durable, redacted local incident events.
It deduplicates unchanged failures, emits bounded reminders and recovery, and
retains unacknowledged evidence without sending notifications or executing an
action. P133 serializes all local operations with an exclusive process lease.

```bash
mkdir -p data/p131
printf '%s\n' '{"timestamp":"2026-07-13T00:00:00Z","service":"demo","message":"healthy"}' > data/p131/telemetry.jsonl

# Keep this foreground command under systemd, launchd, Docker, or another process supervisor.
uv run --no-sync opscat-monitor run --config config/p131-monitor.example.json --forever

# Run independently from the monitor process; non-zero means stale/missing/tampered heartbeat.
uv run --no-sync opscat-monitor watchdog --state data/p131/runtime-state.json --timeout-seconds 180
uv run --no-sync opscat-monitor status --state data/p131/runtime-state.json

# Run as a separate supervised process. It watches the P131 state file, not the monitor process itself.
uv run --no-sync opscat-monitor deadman-run --config config/p133-deadman.example.json --forever

# One check exits 0 when healthy, 1 when unhealthy, and 2 on config/storage failure.
uv run --no-sync opscat-monitor deadman-check --config config/p133-deadman.example.json
uv run --no-sync opscat-monitor outbox-list --config config/p133-deadman.example.json
# Acknowledgement is local bookkeeping only; it does not close the active incident.
uv run --no-sync opscat-monitor outbox-ack --config config/p133-deadman.example.json --event-id 'sha256:<64-hex>'
```

The FastAPI app also exposes `GET /monitor/health` and
`GET /monitor/readiness`; either returns HTTP 503 when its contract is not met.
See [`docs/operations/p131-operator-runbook.md`](docs/operations/p131-operator-runbook.md),
[`docs/operations/p132-final-summary.md`](docs/operations/p132-final-summary.md),
[`docs/operations/p133-final-summary.md`](docs/operations/p133-final-summary.md),
and [`docs/operations/p133-local-deadman-outbox-roadmap.md`](docs/operations/p133-local-deadman-outbox-roadmap.md).

Run the bounded supervisor qualification without credentials or network access:

```bash
bash scripts/verify.sh --profile p133-release
```

Example supervisor manifests are under [`deploy/p132`](deploy/p132) and
[`deploy/p133`](deploy/p133). They are
templates, not proof of cloud deployment or a 24/7 production SLO. The Compose
template requires `OPSCAT_MONITOR_IMAGE_DIGEST` and refuses mutable image tags.
P133 qualifies the parsed systemd and Compose isolation contracts. Its launchd
plist is a structurally validated example only because a plist by itself cannot
enforce the same no-network and read-only-monitor-state boundary; macOS use
requires a separately reviewed sandbox or MDM policy.
Auditable bounded raw qualification inputs and outputs are retained under
`evals/p132/raw/` and `evals/p133/raw/`.
P133's outbox is local evidence only: it does not prove notification delivery,
multi-host availability, remediation quality, malicious same-UID writer
resistance, or unattended production operation. Retention requires service-owned,
non-group/world-writable outbox and acknowledgement directories.

## Portfolio demo evidence

OpsCat is designed to demonstrate the architecture of an agentic incident-response loop: tool use, evidence-grounded reasoning, policy and safety gates, autonomous observe-to-report flow, evaluation/benchmarking, human approval handoff, and a local/mock/sandbox-only mutation boundary. It does not prove operator replacement.

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
- [`docs/operations/p103-final-summary.md`](docs/operations/p103-final-summary.md) — multi-step LLM replanning, discovery, and recovery evidence.
- [`docs/operations/p104-final-summary.md`](docs/operations/p104-final-summary.md) — evidence-gap sufficiency, false-handoff, and safety-boundary evidence.
- [`docs/operations/p105-model-card.md`](docs/operations/p105-model-card.md) — P105 forecast model card, mode semantics, metric formulas, provenance scope, and authority limits.
- [`docs/operations/p105-final-summary.md`](docs/operations/p105-final-summary.md) — P105 release-integration summary and P106 lock status.
- [`docs/operations/p106-ticket-roadmap.md`](docs/operations/p106-ticket-roadmap.md) — P106 simulation-only preventive planner roadmap and release gates.
- [`docs/operations/p106-plan-review.md`](docs/operations/p106-plan-review.md) — P106 planning approval with final implementation review pending.
- [`docs/operations/p106-final-summary.md`](docs/operations/p106-final-summary.md) — P106 documentation/release-verification summary without final review claims.
- [`docs/operations/p107-ticket-roadmap.md`](docs/operations/p107-ticket-roadmap.md) — P107 local/mock or isolated canary executor roadmap, release profile, and P108 replay handoff.
- [`docs/operations/p108-ticket-roadmap.md`](docs/operations/p108-ticket-roadmap.md) — P108 immutable offline outcome-learning and promotion roadmap.
- [`docs/operations/p109-real-ops-benchmark-roadmap.md`](docs/operations/p109-real-ops-benchmark-roadmap.md) — P109 real telemetry and independently verified remediation benchmark roadmap.
- [`docs/operations/p111-final-summary.md`](docs/operations/p111-final-summary.md) — frozen blind RCA accuracy results, paired deltas, calibration, and remaining release gates.
- [`docs/operations/p110-final-summary.md`](docs/operations/p110-final-summary.md) — official labeled RCAEval holdout, real NVIDIA metrics, safety counters, and honest limitations.
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

## Multi-step LLM diagnostic episode (P103)

```bash
uv run --no-sync --extra dev python scripts/run_llm_diagnostic_episode.py \
  --max-cases 52 --obvious-only --sample-size 5 \
  --output-json /tmp/opscat-p103-mock.json

# Explicit opt-in external model; read-only diagnostic choice only.
uv run --no-sync --extra dev python scripts/run_llm_diagnostic_episode.py \
  --max-cases 52 --obvious-only --sample-size 5 --include-nvidia \
  --output-json /tmp/opscat-p103-nvidia.json
```

P103 passes negative read-only results back to the planner, removes attempted tools,
and allows up to three distinct diagnostics before safe escalation. In the recorded
52-family NVIDIA run, first-tool accuracy was 76.92%, multi-step discovery reached
98.08%, and final recovery matched the heuristic investigator at 76.92%. The model
made 67 advisory decisions and executed zero actions.

## Evidence gap investigator (P104)

```bash
uv run --no-sync --extra dev python scripts/run_evidence_gap_investigator.py \
  --max-cases 10 --sample-size 10 --seeds 11,29,47 \
  --output-json /tmp/opscat-p104-evidence-gap-investigator-full.json \
  --output-md /tmp/opscat-p104-evidence-gap-investigator-full.md
```

P104 checks whether evidence is fresh, sufficient, cited, non-conflicting, and
available before any policy handoff. The default run is deterministic,
network-free, model-call-free, advisory for optional provider use, and action
disabled. In the recorded full committed fixture run, P104's false-remediation
handoff rate was 0/27 = 0.0 versus 3/27 = 0.1111111111111111 for P103,
with provider action execution count 0/150 and production mutation count 0/150.
It distinguishes valid absence from unavailable telemetry with denominators
1 and 2, and does not claim production effectiveness or unattended operation.

## P105 calibrated failure forecast smoke

P105 is a calibrated failure forecast engine, not an action planner. The
committed P105 fixture remains a tiny `smoke_only_missing_mode` wiring fixture:
it proves local formulas, partition separation, diagnostics, and command
integration only. It is not release-qualified performance evidence and must not
unlock P106.

Run the offline benchmark smoke:

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark evals/proactive/forecast/p105_release_benchmark_rows.json \
  --output-json /tmp/opscat-p105-release-benchmark-smoke.json
```

P105 release qualification requires explicit `mode=release_qualified`,
per-family held-out and real-derived denominator floors, source-record
provenance from P32/P41/P44 materialized records, outcome-neutral partitions,
unioned service-day denominators from coverage intervals and covered seconds,
actual P24 `RiskSignal`/`RiskForecast` parity, and zero authority counters. The
floors are anti-tiny-N credibility checks, not statistical significance claims.
See
[`docs/operations/p105-ticket-roadmap.md`](docs/operations/p105-ticket-roadmap.md),
[`docs/operations/p105-model-card.md`](docs/operations/p105-model-card.md),
[`docs/operations/p105-final-summary.md`](docs/operations/p105-final-summary.md),
and [`docs/tickets/p105/README.md`](docs/tickets/p105/README.md).

## P106 preventive action planner verification lane

P106 is a simulation-only preventive planning layer. It requires canonical P105
release-qualified evidence and P104 sufficient evidence before candidate
scoring, then composes the shared registry, policy engine, simulator,
blast-radius service, and incident memory. It does not execute remediation,
create auth scope, mutate production, or give optional LLM advisory packets any
decision authority.

Run the offline benchmark smoke with the SHA-pinned real-derived P105 fixture:

```bash
tmpdir="$(mktemp -d)"
cleanup() { rm -rf -- "$tmpdir"; }
trap cleanup EXIT INT TERM
p105_artifact="$(uv run --no-sync --extra dev python \
  scripts/extract_p105_release_fixture.py \
  evals/prevention/p105_release_qualified_real_derived.tar.gz \
  6aaf35285f03cc7fe68b036a8172dba1615d1e5131939b2d8ef26787dd5c7342 \
  "$tmpdir/p105")"
uv run --no-sync --extra dev python scripts/run_preventive_action_benchmark.py \
  --cases evals/prevention/p106_benchmark_cases.json \
  --p105-artifact "$p105_artifact" \
  --output-json "$tmpdir/opscat-p106-preventive-action-benchmark.json" \
  --output-md "$tmpdir/opscat-p106-preventive-action-benchmark.md"
```

The fresh run is scored with one eligible planner evaluation, zero regret and
harm, safe-fallback and fail-closed rates of `1.0`, one mutation-shaped
simulation-only plan, and zero authority. Prior verifier findings are fixed and
covered by targeted tests. The evidence is eligible for the P107 conjunctive
gate, but P106 itself keeps `p107_unlocked=false` and grants no execution
authority. Final independent implementation code and architecture/safety review
remain pending until the leader supplies results.

See [`docs/operations/p106-ticket-roadmap.md`](docs/operations/p106-ticket-roadmap.md)
and [`docs/tickets/p106/README.md`](docs/tickets/p106/README.md).

## P107 canary prevention executor verification lane

P107 is scoped to local/mock or isolated test-harness canary execution. It
consumes P106 gate-eligible evidence only after recomputing the canonical P106
gate, while P106 itself continues to report `p107_unlocked=false`. P107 does
not create auth scope, read credentials, call networks, run shell commands,
mutate cloud or databases, use production adapters, or perform production
mutation.

Run the canonical release profile:

```bash
bash scripts/verify.sh --profile p107-release
```

That profile includes all 15 targeted P107 release test files and the
`scripts/run_prevention_canary_evidence.py` smoke against
`evals/prevention/p107_canary_cases.json`. The evidence is valid only for
local/mock or isolated behavior. P108 receives a handoff only from deterministic
terminal replay evidence with matching independent review JSON; missing review
evidence keeps `p108_replay_gate_ready=false`.

See [`docs/operations/p107-ticket-roadmap.md`](docs/operations/p107-ticket-roadmap.md)
and [`docs/tickets/p107/README.md`](docs/tickets/p107/README.md).

## P108 prevention outcome learner verification lane

P108 consumes raw P107 evidence, recomputes its trust boundary, records a
content-bound outcome ledger, assigns conservative counterfactual labels and
credit, and emits versioned recommendations that always remain `applied=false`.
It cannot access databases, credentials, networks, shells, executors, live
adapters, or online policy/runbook/prompt mutation.

```bash
bash scripts/verify.sh --profile p108-release
```

The profile validates the exact L01-L16 fixture matrix, six paired holdout
cells, per-family safety and drift gates, exact-zero authority, deterministic
CLI output, and fresh non-self independent-review bindings. See
[`docs/operations/p108-ticket-roadmap.md`](docs/operations/p108-ticket-roadmap.md)
and [`docs/tickets/p108/README.md`](docs/tickets/p108/README.md).

## P109 real operations benchmark lane

P109 adds fail-closed import and evaluation for public RCA telemetry and
externally executed remediation results. The pinned Baro/RCAEval sample is real
upstream telemetry; it contains no official root-cause truth, so OpsCat reports
it as parser smoke evidence rather than inventing an accuracy score.

```bash
uv run --no-sync python scripts/run_rcaeval_real_sample.py
bash scripts/verify.sh --profile p109-release
```

The sample currently yields 41,097 metric observations across 13 services and
status `unevaluable_real_data_missing`. A real release additionally requires
official diagnosis labels, independently verified external remediation runs,
nonzero per-system/fault-family denominators, complete artifact hashes, and a
non-self review. P109 has no Kubernetes, Ansible, shell, credential, database,
cloud, production-mutation, or remediation-execution authority.

See [`docs/operations/p109-real-ops-benchmark-roadmap.md`](docs/operations/p109-real-ops-benchmark-roadmap.md)
and [`docs/tickets/p109/README.md`](docs/tickets/p109/README.md).

## P114 RE2 acquisition metadata lane

P114 pins official Zenodo record 14590730 metadata for RCAEval `RE2-SS.zip`
and `RE2-OB.zip`. Normal verification does not download external archives; the
local validator checks the exact file name, compressed byte size, upstream MD5,
computes SHA-256 for the acquired bytes, and rejects unsafe zip metadata
including traversal, symlinks, duplicate entries, and decompression budget
excess before case-layout parsing.

```bash
python scripts/acquire_p114_rcaeval.py --source re2-ss
python scripts/acquire_p114_rcaeval.py --source re2-ob
```

Downloads are opt-in only via `--allow-network`; OpsCat does not redistribute
the RE2 archives.

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

## P134 observation-authority contract

OpsCat now separates read-only observation permission from action authority with
strict `OA0`/`OA1` contracts, hash-bound structural review receipts, immutable
decision receipts, deterministic budget accounting, replay protection, and a
fail-closed 24-case release matrix.

```bash
bash scripts/verify.sh --profile p134-release
```

P134 is policy-only. It performs no file ingestion, provider request, live GET,
credential access, notification delivery, command execution, remediation, or
staging/production mutation. P135 is the first phase allowed to consume the
qualified local-artifact policy for credential-free provider-shaped exports.

## P135 credential-free provider-shaped export attachment

P135 consumes only bounded local files authorized by a current P134
`OA1_LOCAL_ARTIFACT` receipt. Versioned adapters normalize Prometheus range,
Loki streams, Grafana dashboards, Sentry issue lists, and OTLP metrics JSONL
into independently validated P120 evidence records. Descriptor-relative reads,
content and identity checks, strict parser budgets, immutable execution
receipts, duplicate revalidation, denominator-visible failures, and a runtime
forbidden-authority guard keep attachment fail closed.

```bash
bash scripts/verify.sh --profile p135-release
```

The canonical matrix passes 30/30 cases: five provider-shaped attachments, one
secure duplicate, and 24 rejection/adversarial cases. P135 reads local fixture
artifacts only. It makes no provider, network, DNS, socket, credential,
environment, subprocess, shell, delivery, remediation, staging/production
mutation, or operator-replacement claim.

## P136 crash-safe incremental local observer

P136 watches one explicitly configured append-only local JSONL index under a
finite pool of P134 `OA1_LOCAL_ARTIFACT` receipts. It durably reserves an index
read before opening the file, verifies consumed-prefix and rotation continuity,
defers incomplete lines, resolves durable duplicates before segment access, and
routes each first-seen segment through the real P135 adapter with an independent
manifest, execution receipt, normalized bundle, and receipt ledger.

```bash
bash scripts/verify.sh --profile p136-release
```

The source-bound release profile executes a fixed 50-case denominator and proves
five real first-batch provider promotions, exact-zero forbidden authority, zero
duplicate promotions/segment reads, bounded resource use, and a current
independent review with no unresolved P0/P1/P2 findings. This milestone remains
local-artifact observation only: it adds no provider API call, credential read,
environment discovery, network access, notification, command execution,
remediation, staging/production mutation, or operator-replacement authority.
