# OpsCat P4 Release Evidence Index

This index maps the P4 portfolio claim to the exact local commands, tests, generated artifacts, and safety boundaries that support it.

## Primary release gate

Run the full local release gate:

```bash
bash scripts/verify.sh
```

The gate currently runs:

1. Python bytecode compile for `app`, `tests`, and `scripts`.
2. Ruff lint for `app`, `tests`, and `scripts`.
3. Mypy typecheck for `app`, `tests`, and `scripts`.
4. Full pytest regression suite.
5. Coverage gate via `scripts/coverage_gate.py`.
6. Golden incident evals via `scripts/run_evals.py`.
7. Connector eval runner via `scripts/run_connector_evals.py`.
8. Local deterministic demo smoke.
9. Docker Compose config validation.
10. Tracked generated artifact scan.
11. Whitespace diff check.


## Verification profiles

Use named profiles when running locally or in CI:

```bash
bash scripts/verify.sh --profile fast
bash scripts/verify.sh --profile full
bash scripts/verify.sh --profile eval
bash scripts/verify.sh --profile docs
```

- `fast`: compile, lint, typecheck, and pytest.
- `full`: complete release gate; this remains the default when no profile is supplied.
- `eval`: golden incident evals plus connector evals.
- `docs`: documentation contract tests plus repository hygiene checks.

GitHub Actions runs the secret-free full profile from `.github/workflows/ci.yml`.

## P4 evidence artifacts

| Claim | Gate | Artifact |
| --- | --- | --- |
| Incident agent loop is reproducibly evaluated | `scripts/run_evals.py` | `/tmp/opscat-evals-latest.md`, `/tmp/opscat-evals.json` |
| Connector calls fail closed and preserve idempotency | `scripts/run_connector_evals.py` | `/tmp/opscat-connector-evals-latest.md`, `/tmp/opscat-connector-evals.json` |
| P5 connector product readiness covers setup, permissions, secret lifecycle, and incident import normalization | `tests/test_connector_evals.py` + `scripts/run_connector_evals.py` | connector eval JSON/Markdown categories: `setup_permission`, `setup_failure`, `import_normalization` |
| Dashboard is navigable and safe enough for demo review | `tests/test_operator_dashboard_e2e.py` | pytest output |
| Golden corpus coverage cannot silently narrow | `tests/test_eval_coverage_taxonomy.py` | `docs/eval-taxonomy.json` |
| Reviewer-facing narrative is stable | `tests/test_portfolio_evidence_docs.py` | `docs/eval-report.md` |
| Release evidence map is stable | `tests/test_release_evidence_index.py` | `docs/release-evidence.md` |


## Versioned release evidence snapshot

Before tagging or publishing an OSS snapshot, run the full local gate:

```bash
bash scripts/verify.sh --profile full
```

This versioned release evidence snapshot should reference:

- `docs/release-evidence.md`;
- `CHANGELOG.md`;
- `docs/deployment-dry-run.md`;
- `/tmp/opscat-evals-latest.md`;
- `/tmp/opscat-connector-evals-latest.md`;
- the current git commit SHA.

stable vs experimental status is documented in `CHANGELOG.md` and `docs/deployment-dry-run.md`.

## Manual artifact commands

Golden incident evals:

```bash
python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md
```

Connector evals:

```bash
python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md
```

Dashboard browser-contract E2E:

```bash
pytest tests/test_operator_dashboard_e2e.py -q
```

Taxonomy and portfolio docs:

```bash
pytest tests/test_eval_coverage_taxonomy.py tests/test_portfolio_evidence_docs.py tests/test_release_evidence_index.py -q
```

## Safety boundary

No real external side effects are permitted in P4.

- No real Slack/GitHub/Sentry side effects.
- No production rollback.
- No Kubernetes/cloud/database/shell mutation product tool.
- No real customer data.
- No production credential material.

The P4 evidence demonstrates the local/mock architecture and release discipline. P5 must add production authentication, real connector deployment, credential/OAuth operations, CI, hosted workflow workers, real incident replay, load/soak testing, and security review before paid customer production use.

## P5 final release evidence

P5 final release evidence was closed with the local/mock OSS productization scope complete and auth remains deferred. The final gate is:

```bash
bash scripts/verify.sh --profile full
```

Expected terminal evidence includes `Verification complete (full)`.

Completed P5 tickets:

- P5-001
- P5-002
- P5-003
- P5-004
- P5-005
- P5-006
- P5-007
- P5-008
- P5-009
- P5-010
- P5-011
- P5-012
- P5-013
- P5-014
- P5-015
- P5-016
- P5-017
- P5-018

P5 remains local/mock: no production credential material, live provider mutation, hosted auth, or real customer production deployment is claimed.

## P6 Agentic Loop Evidence

- Roadmap: `docs/operations/p6-ticket-roadmap.md`
- Final summary: `docs/operations/p6-final-summary.md`
- Agentic loop docs: `docs/agentic-loop.md`
- Demo command: `uv run --no-sync --extra dev python scripts/demo_agentic_loop.py`
- Agentic eval command: `python scripts/run_agentic_evals.py --output-json /tmp/opscat-agentic-evals.json --output-md /tmp/opscat-agentic-evals.md`
- Latest temp eval artifact: `/tmp/opscat-agentic-evals-latest.md`
- Security review: `docs/security-review-p6.md`
- Safety policy: `docs/operations/safety-policy.md`
- Verification command: `bash scripts/verify.sh --profile full`

P6 keeps auth deferred and does not claim production readiness or unattended production mutation safety.

## P7 Reliability & Safety Lab Evidence

- Roadmap: `docs/operations/p7-ticket-roadmap.md`
- Final summary: `docs/operations/p7-final-summary.md`
- Security review: `docs/security-review-p7.md`
- Replay command: `python scripts/run_replay_evals.py --output-json /tmp/opscat-replay-evals.json --output-md /tmp/opscat-replay-evals.md`
- Targeted P7 tests: `pytest -q tests/test_p7_reliability_lab.py`
- Full release gate: `bash scripts/verify.sh --profile full`

P7 remains local/mock and auth-deferred. It adds replay, adversarial evals, confidence calibration, self-critique, blast-radius classification, action simulation, incident memory, Night Autopilot v2 gates, failure-mode reporting, and reliability dashboard metrics without claiming unattended production operation.

## P7 Agent Reliability & Safety Lab Evidence
- docs/operations/p7-ticket-roadmap.md
- docs/operations/p7-final-summary.md
- docs/security-review-p7.md
- scripts/run_replay_evals.py
- /tmp/opscat-replay-evals-latest.md
This does not claim unattended production operation.


## P8 AI Incident Responder War Room Evidence

- Roadmap: `docs/operations/p8-ticket-roadmap.md`
- Final summary: `docs/operations/p8-final-summary.md`
- Demo script: `docs/operations/p8-demo-script.md`
- Security review: `docs/security-review-p8.md`
- Demo tests: `tests/test_p8_demo.py`
- Security docs tests: `tests/test_p8_security_docs.py`
- Release evidence tests: `tests/test_p8_release_evidence.py`
- Replay evidence command: `python scripts/run_replay_evals.py --output-json /tmp/opscat-replay-evals.json --output-md /tmp/opscat-replay-evals.md`
- Demo command: `uv run --no-sync --extra dev python scripts/demo.py`
- Full release gate: `bash scripts/verify.sh --profile full`

P8 remains local/mock and auth-deferred. It presents war room reasoning, reliability score, runbook critique, human questions, action gates, and report links as reviewer evidence; it does not claim unattended production operation.

## P9 Autonomous Incident Commander Evidence

- Roadmap: `docs/operations/p9-ticket-roadmap.md`
- Final summary: `docs/operations/p9-final-summary.md`
- Security review: `docs/security-review-p9.md`
- Commander service tests: `tests/test_incident_commander.py`
- Response planner tests: `tests/test_response_planner.py`
- Autonomy readiness tests: `tests/test_autonomy_readiness.py`
- Evidence graph tests: `tests/test_evidence_graph.py`
- Recovery verifier tests: `tests/test_recovery_verifier_v2.py`
- Learning loop tests: `tests/test_commander_learning.py`
- Commander tournament tests: `tests/test_p9_commander_tournament.py`
- Commander safety tests: `tests/test_p9_commander_safety.py`
- Commander UI tests: `tests/test_p9_commander_ui.py`
- Tournament command: `uv run --no-sync --extra dev python scripts/run_commander_tournament.py --output-json /tmp/opscat-p9-commander-tournament.json`
- Latest temp tournament artifact: `/tmp/opscat-p9-commander-tournament-latest.json`
- Full release gate: `bash scripts/verify.sh --profile full`

P9 remains local/mock and auth-deferred. It adds an Autonomous Incident Commander lifecycle, multi-step response planning, autonomy-readiness scoring, evidence graph modeling, recovery verification v2, learning from prior outcomes, commander tournament evals, operator UI evidence, and safety regression tests. It does not claim unattended production operation.

## P10 Incident Judgment Benchmark Evidence

- Roadmap: `docs/operations/p10-ticket-roadmap.md`
- Final summary: `docs/operations/p10-final-summary.md`
- Dataset schema tests: `tests/test_judgment_dataset.py`
- Adapter tests: `tests/test_judgment_adapters.py`
- Evaluator tests: `tests/test_judgment_evaluator.py`
- Benchmark tests: `tests/test_judgment_benchmark.py`
- CLI tests: `tests/test_judgment_cli.py`
- Release evidence tests: `tests/test_p10_release_evidence.py`
- Dataset conversion command: `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/import_judgment_dataset.py --source loghub --input <fixture> --output /tmp/opscat-judgment-cases.json`
- Benchmark command: `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_judgment_benchmark.py --output-json /tmp/opscat-judgment-benchmark.json --output-md /tmp/opscat-judgment-benchmark.md`
- Latest temp benchmark artifact: `/tmp/opscat-judgment-benchmark-latest.md`
- Full release gate: `bash scripts/verify.sh --profile full`

P10 remains local/mock and auth-deferred. It adds a deterministic benchmark for incident judgment quality using repo-local seed cases; it does not download public datasets during normal verification and does not claim unattended production operation.

## P11 Incident Corpus Expansion Evidence

- Roadmap: `docs/operations/p11-ticket-roadmap.md`
- Final summary: `docs/operations/p11-final-summary.md`
- Corpus service tests: `tests/test_judgment_corpus.py`
- Corpus CLI tests: `tests/test_judgment_corpus_cli.py`
- Release evidence tests: `tests/test_p11_release_evidence.py`
- Corpus service: `app/services/judgment_corpus.py`
- Corpus CLI: `scripts/run_corpus_audit.py`
- Corpus fixture: `evals/judgment/corpus/p11-corpus.json`
- Corpus audit command: `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_corpus_audit.py --corpus evals/judgment/corpus/p11-corpus.json --output-json /tmp/opscat-corpus-audit.json --output-md /tmp/opscat-corpus-audit.md`
- Latest temp corpus audit artifact: `/tmp/opscat-corpus-audit-latest.md`
- Full release gate: `bash scripts/verify.sh --profile full`

P11 remains local/mock and auth-deferred. It expands incident judgment coverage before LLM attachment; it does not download public datasets during normal verification and does not claim unattended production operation.

## P12 Real Dataset Evaluation Harness Evidence

- Roadmap: `docs/operations/p12-ticket-roadmap.md`
- Final summary: `docs/operations/p12-final-summary.md`
- Real dataset service tests: `tests/test_real_dataset_evaluation.py`
- Real dataset CLI tests: `tests/test_real_dataset_cli.py`
- Release evidence tests: `tests/test_p12_release_evidence.py`
- Dataset service: `app/services/real_dataset_evaluation.py`
- Conversion CLI: `scripts/import_real_dataset.py`
- Evaluation CLI: `scripts/run_real_dataset_eval.py`
- Fixture manifest: `evals/real_datasets/fixtures/manifest.json`
- Fixture evaluation command: `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_real_dataset_eval.py --fixture-pack --output-json /tmp/opscat-real-dataset-eval.json --output-md /tmp/opscat-real-dataset-eval.md --output-cases /tmp/opscat-real-dataset-cases.json`
- Latest temp real dataset eval artifact: `/tmp/opscat-real-dataset-eval-latest.md`
- Full release gate: `bash scripts/verify.sh --profile full`

P12 remains local/mock and auth-deferred. It evaluates tiny real-dataset-shaped fixtures through the existing deterministic benchmark; it does not download public datasets during normal verification and does not claim unattended production operation.


## P13 LLM Context Builder Evidence

P13 adds a deterministic pre-LLM context builder so future model judgment receives redacted, evidence-cited, safety-constrained incident context. It remains local/mock and performs no model calls.

Artifacts:

- `docs/operations/p13-ticket-roadmap.md`
- `docs/operations/p13-final-summary.md`
- `app/services/llm_context_builder.py`
- `scripts/build_llm_context.py`
- `tests/test_llm_context_builder.py`
- `tests/test_llm_context_cli.py`
- `tests/test_p13_release_evidence.py`
- `/tmp/opscat-llm-context-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_context_builder.py tests/test_llm_context_cli.py tests/test_p13_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock; no external model/API calls; no production mutation; no Kubernetes/cloud/database mutation; no unrestricted shell; no unattended production-operation claim.


## P14 LLM Judgment Adapter Evidence

P14 adds a mock-by-default LLM Judgment Adapter so OpsCat can evaluate model-shaped incident judgment without handing authority to model text. Provider output is schema-validated, evidence-citation checked, safety-gated, and never used to execute actions.

Artifacts:

- `docs/operations/p14-ticket-roadmap.md`
- `docs/operations/p14-final-summary.md`
- `app/services/llm_judgment.py`
- `scripts/run_llm_judgment.py`
- `tests/test_llm_judgment.py`
- `tests/test_llm_judgment_cli.py`
- `tests/test_p14_release_evidence.py`
- `/tmp/opscat-llm-judgment-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_judgment.py tests/test_llm_judgment_cli.py tests/test_p14_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock; no default external model/API calls; no production mutation; no Kubernetes/cloud/database mutation; no unrestricted shell; no action execution; no unattended production-operation claim.


## P15 NVIDIA LLM Provider Opt-in Evidence

P15-mini adds an explicit live-provider path for NVIDIA Build/OpenAI-compatible chat completions while keeping normal verification mock/offline. The provider uses `nvidia/nemotron-3-ultra-550b-a55b` by default, reads `NVIDIA_API_KEY`, allows `OPSCAT_NVIDIA_MODEL`, and remains behind P14 schema validation, evidence citation checking, and safety gate.

Artifacts:

- `docs/operations/p15-ticket-roadmap.md`
- `docs/operations/p15-final-summary.md`
- `app/services/llm_judgment.py`
- `scripts/run_llm_judgment.py`
- `tests/test_nvidia_llm_provider.py`
- `tests/test_p15_release_evidence.py`

Live opt-in example:

```bash
export NVIDIA_API_KEY="..."
# install/use the optional live provider dependency with uv run --extra llm
OPSCAT_NVIDIA_MODEL=nvidia/nemotron-3-ultra-550b-a55b \
uv run --extra llm python scripts/run_llm_judgment.py \
  --cases evals/judgment/seed/cases.json \
  --case-id seed-loghub-injection-block \
  --provider nvidia \
  --output-json /tmp/opscat-nvidia-judgment.json \
  --output-md /tmp/opscat-nvidia-judgment.md
```

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_nvidia_llm_provider.py tests/test_p15_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no committed keys; no default external model/API calls during verification; no production mutation; no action execution; no unattended production-operation claim.


## P16 LLM Provider Evaluation Evidence

P16 evaluates whether LLM judgment providers are safe and useful across judgment cases, rather than only checking that a provider connects. Normal verification uses the mock provider; NVIDIA live evaluation remains explicit opt-in.

Artifacts:

- `docs/operations/p16-ticket-roadmap.md`
- `docs/operations/p16-final-summary.md`
- `app/services/llm_provider_evaluation.py`
- `scripts/run_llm_provider_eval.py`
- `tests/test_llm_provider_evaluation.py`
- `tests/test_p16_release_evidence.py`
- `/tmp/opscat-llm-provider-eval-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_provider_evaluation.py tests/test_p16_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Live NVIDIA opt-in:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --extra llm python scripts/run_llm_provider_eval.py \
  --cases evals/judgment/seed/cases.json \
  --provider nvidia \
  --env-file .env \
  --max-cases 4 \
  --output-json /tmp/opscat-nvidia-provider-eval.json \
  --output-md /tmp/opscat-nvidia-provider-eval.md
```

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no action execution; no unattended production-operation claim.

## P17 LLM Policy Calibration Evidence

P17 adds deterministic policy calibration after LLM judgment and safety gating. Provider recommendations remain advisory; OpsCat scores and reports the calibrated route while preserving the raw provider route for audit.

Artifacts:

- `docs/operations/p17-ticket-roadmap.md`
- `docs/operations/p17-final-summary.md`
- `app/services/policy_calibrator.py`
- `app/services/llm_provider_evaluation.py`
- `tests/test_policy_calibrator.py`
- `tests/test_p17_release_evidence.py`
- `/tmp/opscat-policy-calibration-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_policy_calibrator.py tests/test_p17_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no action execution; no unattended production-operation claim.

## P18A Realtime Source Reader Evidence

P18A adds source-native incremental local/mock ingestion for logs and metrics. Runtime readers process original files incrementally, maintain rolling windows, detect triggers, and emit JSON evidence snapshots only for judgment, replay, and audit.

Artifacts:

- `docs/operations/p18a-ticket-roadmap.md`
- `docs/operations/p18a-final-summary.md`
- `app/services/realtime_source_reader.py`
- `scripts/replay_realtime_sources.py`
- `tests/test_realtime_source_reader.py`
- `tests/test_p18a_release_evidence.py`
- `/tmp/opscat-realtime-replay-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_realtime_source_reader.py tests/test_p18a_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no action execution; no unattended production-operation claim.

## P18B Model Judgment Quality Lab Evidence

P18B measures raw model judgment quality separately from P17 policy-calibrated OpsCat decisions. It reports raw_provider_score, calibrated_score, calibration_delta, quality dimension averages, failure taxonomy, calibration wins, and per-case evidence for seed cases plus optional P18A realtime snapshots.

Artifacts:

- `docs/operations/p18b-ticket-roadmap.md`
- `docs/operations/p18b-final-summary.md`
- `app/services/model_quality_lab.py`
- `scripts/run_model_quality_eval.py`
- `tests/test_model_quality_lab.py`
- `tests/test_p18b_release_evidence.py`
- `/tmp/opscat-model-quality-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_model_quality_lab.py tests/test_p18b_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Live NVIDIA opt-in:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --extra llm python scripts/run_model_quality_eval.py \
  --cases evals/judgment/seed/cases.json \
  --p18a-replay-json /tmp/opscat-realtime-real-cache-p18a.json \
  --provider nvidia \
  --env-file .env \
  --max-cases 6 \
  --output-json /tmp/opscat-nvidia-model-quality-p18b.json \
  --output-md /tmp/opscat-nvidia-model-quality-p18b.md
```

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no action execution; no unattended production-operation claim.

## P19 Operator Judgment Improvement Loop Evidence

P19 converts P18B model-quality failures into operator-grade improvement plans. It prioritizes failures, emits non-mutating recommendations, plans safe missing-evidence collection, writes regression packs, and compares before/after quality reports without hiding raw model defects behind policy calibration.

Artifacts:

- `docs/operations/p19-ticket-roadmap.md`
- `docs/operations/p19-final-summary.md`
- `app/services/operator_improvement_loop.py`
- `scripts/run_improvement_loop.py`
- `tests/test_operator_improvement_loop.py`
- `tests/test_p19_release_evidence.py`
- `/tmp/opscat-improvement-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_improvement_loop.py tests/test_p19_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no action execution; no unattended production-operation claim.

## P20 Closed-loop Agentic Incident Response Evidence

P20 connects observation, initial_judgment, evidence_fetch, revised_judgment, action_proposal, simulation, and final_decision into one local/mock agentic incident response loop. It executes only read-only diagnostic evidence tools and simulates proposed actions without execution.

Artifacts:

- `docs/operations/p20-ticket-roadmap.md`
- `docs/operations/p20-final-summary.md`
- `app/services/closed_loop_response.py`
- `scripts/run_closed_loop_response.py`
- `tests/test_closed_loop_response.py`
- `tests/test_p20_release_evidence.py`
- `/tmp/opscat-closed-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_closed_loop_response.py tests/test_p20_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no action execution; no unattended production-operation claim.

## P21 Runtime Loop Runner and Operator Control Plane Evidence

P21 wraps P20 closed-loop response in a bounded local/mock runtime with queue state, tick processing, approval profile enforcement, pause/resume/abort controls, CLI reports, and verification smoke.

Artifacts:

- `docs/operations/p21-ticket-roadmap.md`
- `docs/operations/p21-final-summary.md`
- `app/services/runtime_loop_control.py`
- `scripts/run_runtime_loop.py`
- `tests/test_runtime_loop_control_plane.py`
- `tests/test_p21_release_evidence.py`
- `/tmp/opscat-runtime-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_runtime_loop_control_plane.py tests/test_p21_release_evidence.py`
- `bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P22 Night-shift Runtime Drill and SLA Scoring Evidence

P22 evaluates the P21 runtime loop as a local/mock night-shift operator with batch incident drills, SLA scoring, safety scoring, CLI reports, and verification smoke.

Artifacts:

- `docs/operations/p22-ticket-roadmap.md`
- `docs/operations/p22-final-summary.md`
- `app/services/night_shift_drill.py`
- `scripts/run_night_shift_drill.py`
- `tests/test_night_shift_drill.py`
- `tests/test_p22_release_evidence.py`
- `/tmp/opscat-night-drill-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_night_shift_drill.py tests/test_p22_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P23 Incident Scenario Corpus Expansion Evidence

P23 expands the local/mock judgment and night-shift drill corpus to 70 scenarios, exceeding the 60 scenarios target with broad incident taxonomy coverage, at least 10 DB connection-pool scenarios, safety/adversarial cases, evidence integrity contracts, and verification integration.

Artifacts:

- `docs/operations/p23-ticket-roadmap.md`
- `docs/operations/p23-final-summary.md`
- `evals/judgment/seed/cases.json`
- `tests/test_p23_scenario_corpus.py`
- `tests/test_p23_release_evidence.py`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_p23_scenario_corpus.py tests/test_p23_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P24 Proactive Risk Sentinel Evidence

P24 adds proactive pre-incident risk forecasting with deterministic local/mock trend windows, ETA/confidence signals, preventive action plans, CLI reports, verification smoke, and release evidence.

Artifacts:

- `docs/operations/p24-ticket-roadmap.md`
- `docs/operations/p24-final-summary.md`
- `app/services/proactive_risk_sentinel.py`
- `scripts/run_proactive_risk_sentinel.py`
- `evals/proactive/seed/risk_windows.json`
- `tests/test_proactive_risk_sentinel.py`
- `tests/test_p24_release_evidence.py`
- `/tmp/opscat-proactive-risk-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_proactive_risk_sentinel.py tests/test_p24_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P25 Proactive Signal Corpus Expansion and Calibration Evidence

P25 expands proactive pre-incident fixtures to 120 local/mock windows across 42 risk types, adds expected outcome metadata, calibration evaluation, CLI reports, verification smoke, and release evidence.

Artifacts:

- `docs/operations/p25-ticket-roadmap.md`
- `docs/operations/p25-final-summary.md`
- `app/services/proactive_risk_sentinel.py`
- `scripts/run_proactive_calibration.py`
- `evals/proactive/seed/risk_windows.json`
- `tests/test_p25_proactive_corpus_calibration.py`
- `tests/test_p25_release_evidence.py`
- `/tmp/opscat-proactive-calibration-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_p25_proactive_corpus_calibration.py tests/test_p25_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P26 Real Telemetry Adapter Contract Evidence

P26 adds read-only fixture adapters for Prometheus/Grafana, Datadog, and Sentry shaped payloads. The adapters normalize telemetry series/events/snapshots, create proactive `TrendWindow` inputs, emit CLI reports, and preserve the no-auth/local-mock safety boundary.

Artifacts:

- `docs/operations/p26-ticket-roadmap.md`
- `docs/operations/p26-final-summary.md`
- `app/services/telemetry_adapter.py`
- `scripts/run_telemetry_adapter.py`
- `evals/telemetry/fixtures/prometheus_query_range.json`
- `evals/telemetry/fixtures/datadog_timeseries.json`
- `evals/telemetry/fixtures/sentry_issues.json`
- `tests/test_telemetry_adapter_contract.py`
- `tests/test_p26_release_evidence.py`
- `/tmp/opscat-telemetry-adapter-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_telemetry_adapter_contract.py tests/test_p26_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 76.68%; P26 telemetry adapter smoke wrote `/tmp/opscat-telemetry-adapter-latest.md` with 3 snapshots, 5 series, 3 events, and 6 trend windows.

Boundary: no-auth/local-mock by default; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P27 Connector Readiness and Permission Contract Evidence

P27 adds read-only connector readiness checks before live-like polling. It evaluates capability manifests, credential references, health state, retry/backoff posture, mutation capability risk, CLI reports, verification smoke, and release evidence.

Artifacts:

- `docs/operations/p27-ticket-roadmap.md`
- `docs/operations/p27-final-summary.md`
- `app/services/connector_readiness.py`
- `scripts/run_connector_readiness.py`
- `evals/connectors/readiness/read_only_sources.json`
- `evals/connectors/readiness/unsafe_sources.json`
- `evals/connectors/readiness/degraded_sources.json`
- `tests/test_connector_readiness_contract.py`
- `tests/test_p27_release_evidence.py`
- `/tmp/opscat-connector-readiness-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_connector_readiness_contract.py tests/test_p27_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 76.71%; P27 connector readiness smoke wrote `/tmp/opscat-connector-readiness-latest.md` with 3 sources, 2 ready, 1 degraded, and 0 blocked.

Boundary: no-auth/local-mock by default; no live writes; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P28 Read-only Polling Runtime Evidence

P28 adds a bounded fixture/local polling runtime that consumes P27 readiness, executes only read-only jobs, feeds successful payloads through P26 adapters, emits telemetry snapshots and proactive TrendWindows, and keeps unsafe or degraded sources from polling.

Artifacts:

- `docs/operations/p28-ticket-roadmap.md`
- `docs/operations/p28-final-summary.md`
- `app/services/read_only_polling_runtime.py`
- `scripts/run_read_only_polling.py`
- `evals/polling/jobs/p28_polling_jobs.json`
- `evals/polling/jobs/p28_unsafe_jobs.json`
- `evals/polling/jobs/p28_failure_jobs.json`
- `tests/test_read_only_polling_runtime.py`
- `tests/test_p28_release_evidence.py`
- `/tmp/opscat-read-only-polling-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_read_only_polling_runtime.py tests/test_p28_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 76.85%; P28 read-only polling smoke wrote `/tmp/opscat-read-only-polling-latest.md` with 3 jobs, 2 polled, 1 skipped, 0 blocked, and 4 trend windows.

Boundary: no-auth/local-mock by default; fixture/local transport only; no live API calls; no live writes; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P29 Telemetry-grounded Judgment Quality Evaluation Evidence

P29 measures whether connector telemetry improves incident judgment quality over a non-telemetry baseline. It covers risk identification, route choice, evidence citation, missing-evidence behavior, unsafe-action behavior, and prompt-injection-safe telemetry handling.

Artifacts:

- `docs/operations/p29-ticket-roadmap.md`
- `docs/operations/p29-final-summary.md`
- `app/services/telemetry_judgment_quality.py`
- `scripts/run_telemetry_judgment_eval.py`
- `evals/judgment/telemetry_grounded/p29_cases.json`
- `tests/test_telemetry_judgment_quality.py`
- `tests/test_p29_release_evidence.py`
- `/tmp/opscat-telemetry-judgment-quality-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_telemetry_judgment_quality.py tests/test_p29_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 77.08%; P29 telemetry judgment quality smoke wrote `/tmp/opscat-telemetry-judgment-quality-latest.md` with 8 cases, baseline accuracy 0.35, grounded accuracy 1.0, accuracy delta 0.65, citation pass rate 1.0, and unsafe action count 0.

Boundary: no-auth/local-mock by default; no default external model/API calls during verification; NVIDIA opt-in only; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P30 Controlled Auto-remediation Policy and Simulation Evidence

P30 adds simulation-first controlled auto-remediation policy. It classifies proposed actions, simulates every action before final route, auto-allows only low-risk local/mock actions, requires approval for reversible operational changes, and blocks destructive or adversarial actions.

Artifacts:

- `docs/operations/p30-ticket-roadmap.md`
- `docs/operations/p30-final-summary.md`
- `app/services/controlled_remediation.py`
- `scripts/run_controlled_remediation.py`
- `evals/remediation/p30_drills.json`
- `tests/test_controlled_remediation_policy.py`
- `tests/test_p30_release_evidence.py`
- `/tmp/opscat-controlled-remediation-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_controlled_remediation_policy.py tests/test_p30_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 77.25%; P30 controlled remediation smoke wrote `/tmp/opscat-controlled-remediation-latest.md` with 5 drills, 14 actions, 5 auto-allowed, 3 approval-required, 6 blocked, simulation-before-decision count 14, and unsafe auto action count 0.

Boundary: simulation/local-mock by default; no auth; no unrestricted shell; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; no unattended production-operation claim.

## P31 End-to-End Operator Replacement Drill Evidence

P31 connects P27 connector readiness, P28 read-only polling, P29 telemetry-grounded judgment quality, and P30 controlled remediation simulation into one deterministic local/mock operator replacement drill. It produces a morning operator report and scores whether the agent can replace a night-shift monitoring operator within the current safety boundary.

Artifacts:

- `docs/operations/p31-ticket-roadmap.md`
- `docs/operations/p31-final-summary.md`
- `app/services/operator_replacement_drill.py`
- `scripts/run_operator_replacement_drill.py`
- `evals/operator_replacement/p31_scenarios.json`
- `tests/test_operator_replacement_drill.py`
- `tests/test_p31_release_evidence.py`
- `/tmp/opscat-operator-replacement-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_replacement_drill.py tests/test_p31_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 77.39%; P31 operator replacement smoke wrote `/tmp/opscat-operator-replacement-latest.md` with 4 scenarios, 16 composed stages, operator_replacement_score 1.0, detection success rate 1.0, citation pass rate 1.0, simulation coverage 1.0, unsafe auto action count 0, and blocked dangerous action count 24.

Boundary: local/mock by default; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P32 Real Telemetry Replay Benchmark Evidence

P32 replays local Prometheus/Grafana, Datadog, and Sentry shaped telemetry fixtures through adapter normalization, trend-window detection, telemetry-grounded judgment scoring, and controlled remediation simulation. It is a real telemetry replay benchmark, not a live production autopilot.

Artifacts:

- `docs/operations/p32-ticket-roadmap.md`
- `docs/operations/p32-final-summary.md`
- `app/services/real_telemetry_replay_benchmark.py`
- `scripts/run_real_telemetry_replay_benchmark.py`
- `evals/telemetry/replay/p32_replay_pack.json`
- `tests/test_real_telemetry_replay_benchmark.py`
- `tests/test_p32_release_evidence.py`
- `/tmp/opscat-real-telemetry-replay-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_real_telemetry_replay_benchmark.py tests/test_p32_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 77.61%; P32 real telemetry replay smoke wrote `/tmp/opscat-real-telemetry-replay-latest.md` with 3 sources, 6 trend windows, replay_score 1.0, source coverage 1.0, grounded accuracy 1.0, citation pass rate 1.0, simulation coverage 1.0, unsafe auto action count 0, blocked dangerous action count 2, and prompt-injection case count 1.

Boundary: local/mock by default; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P33 Live Connector Dry-run Harness Evidence

P33 validates live-connector-shaped manifests through local mock probes before live polling. It audits read-only permission posture, schema drift, mock transport health, readiness status, and operator handoff output.

Artifacts:

- `docs/operations/p33-ticket-roadmap.md`
- `docs/operations/p33-final-summary.md`
- `app/services/live_connector_dry_run.py`
- `scripts/run_live_connector_dry_run.py`
- `evals/connectors/dry_run/p33_connectors.json`
- `tests/test_live_connector_dry_run.py`
- `tests/test_p33_release_evidence.py`
- `/tmp/opscat-live-connector-dry-run-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_live_connector_dry_run.py tests/test_p33_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 77.78%; P33 live connector dry-run smoke wrote `/tmp/opscat-live-connector-dry-run-latest.md` with 4 connectors, 2 ready, 1 degraded, 1 blocked, 1 schema drift, connector_health_score 0.812, permission safety rate 0.75, schema compatibility rate 0.75, transport health rate 1.0, readiness rate 0.75, and live API call count 0.

Boundary: dry-run/local by default; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P34 Live Read-only Polling Runtime v2 Evidence

P34 gates read-only polling through P33 dry-run readiness. It polls only ready local fixture jobs, skips degraded/blocked connectors, blocks write/mutation jobs, adapts telemetry payloads, and emits trend windows.

Artifacts:

- `docs/operations/p34-ticket-roadmap.md`
- `docs/operations/p34-final-summary.md`
- `app/services/read_only_polling_v2.py`
- `scripts/run_read_only_polling_v2.py`
- `evals/polling/v2/p34_polling_jobs.json`
- `tests/test_read_only_polling_v2.py`
- `tests/test_p34_release_evidence.py`
- `/tmp/opscat-read-only-polling-v2-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_read_only_polling_v2.py tests/test_p34_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 77.91%; P34 read-only polling v2 smoke wrote `/tmp/opscat-read-only-polling-v2-latest.md` with 5 jobs, 2 polled, 2 skipped, 1 blocked, 2 snapshots, 4 trend windows, poll_success_rate 1.0, readiness gate rate 1.0, unsafe poll count 0, and live API call count 0.

Boundary: read-only/local by default; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P35 Incident Shadow Mode Evidence

P35 records would-do incident decisions from read-only evidence without executing remediation. It produces diagnosis, route, proposed actions, blocked actions, evidence links, and operator handoff reports.

Artifacts:

- `docs/operations/p35-ticket-roadmap.md`
- `docs/operations/p35-final-summary.md`
- `app/services/incident_shadow_mode.py`
- `scripts/run_incident_shadow_mode.py`
- `evals/shadow/p35_shadow_cases.json`
- `tests/test_incident_shadow_mode.py`
- `tests/test_p35_release_evidence.py`
- `/tmp/opscat-incident-shadow-mode-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_incident_shadow_mode.py tests/test_p35_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.04%; `app/services/incident_shadow_mode.py` coverage 89.12%; P35 incident shadow mode smoke wrote `/tmp/opscat-incident-shadow-mode-latest.md` with 4 cases, 4 shadow decisions, expected_route_match_rate 1.0, evidence link rate 1.0, shadow coverage 1.0, execution count 0, and unsafe shadow action count 0.

Boundary: shadow/local by default; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P36 Approval Control Plane Evidence

P36 routes P35 shadow decisions through local approval profiles and records what would be auto-allowed, approval-required, or blocked without executing remediation.

Artifacts:

- `docs/operations/p36-ticket-roadmap.md`
- `docs/operations/p36-final-summary.md`
- `app/services/approval_control_plane.py`
- `scripts/run_approval_control_plane.py`
- `evals/approval/p36_profiles.json`
- `tests/test_approval_control_plane.py`
- `tests/test_p36_release_evidence.py`
- `/tmp/opscat-approval-control-plane-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_approval_control_plane.py tests/test_p36_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.22%; `app/services/approval_control_plane.py` coverage 89.62%; P36 approval control plane smoke wrote `/tmp/opscat-approval-control-plane-latest.md` with 3 profiles, 10 requests, 30 profile decisions, profile coverage 1.0, 6 auto-allowed decisions, 12 approval-required decisions, 12 blocked decisions, 12 blocked-untrusted decisions, unsafe auto action count 0, and execution count 0.

Boundary: approval-control/local by default; no auth/session work; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P37 Open-source Config Hardening Evidence

P37 validates open-source/local configuration templates and examples before real connectors are attached. It checks placeholder usage, safe defaults, secret-marker absence, and disabled live/prod mutation boundaries.

Artifacts:

- `docs/operations/p37-ticket-roadmap.md`
- `docs/operations/p37-final-summary.md`
- `app/services/open_source_config_hardening.py`
- `scripts/run_open_source_config_hardening.py`
- `evals/config/p37_config_manifest.json`
- `config/opscat.local.example.json`
- `config/connectors.local.example.json`
- `tests/test_open_source_config_hardening.py`
- `tests/test_p37_release_evidence.py`
- `/tmp/opscat-open-source-config-hardening-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_open_source_config_hardening.py tests/test_p37_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.31%; `app/services/open_source_config_hardening.py` coverage 86.26%; P37 open-source config hardening smoke wrote `/tmp/opscat-open-source-config-hardening-latest.md` with 4 checked surfaces, 4 passed surfaces, blocker count 0, template pass rate 1.0, secret safety rate 1.0, safe default rate 1.0, real secret count 0, and unsafe default count 0.

Boundary: open-source/local config hardening only; no auth/session implementation; no real `.env` value reads; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P38 Agent Evaluation Dashboard Evidence

P38 aggregates recent local agent evaluation phases into one JSON/Markdown scorecard with phase cards, safety gates, evidence links, and readiness tier.

Artifacts:

- `docs/operations/p38-ticket-roadmap.md`
- `docs/operations/p38-final-summary.md`
- `app/services/agent_evaluation_dashboard.py`
- `scripts/run_agent_evaluation_dashboard.py`
- `evals/dashboard/p38_sources.json`
- `tests/test_agent_evaluation_dashboard.py`
- `tests/test_p38_release_evidence.py`
- `/tmp/opscat-agent-evaluation-dashboard-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_agent_evaluation_dashboard.py tests/test_p38_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.38%; `app/services/agent_evaluation_dashboard.py` coverage 85.55%; P38 agent evaluation dashboard smoke wrote `/tmp/opscat-agent-evaluation-dashboard-latest.md` with 5 phase cards, 5 passed phases, 0 failed phases, boundary violation count 0, overall score 0.962, and readiness tier portfolio-ready.

Boundary: local dashboard artifact only; no hosted dashboard requirement; no auth/session work; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P39 Runbook Learning Loop Evidence

P39 converts local evaluation signals into runbook improvement recommendations and regression cases without automatically editing production runbooks or executing remediation.

Artifacts:

- `docs/operations/p39-ticket-roadmap.md`
- `docs/operations/p39-final-summary.md`
- `app/services/runbook_learning_loop.py`
- `scripts/run_runbook_learning_loop.py`
- `evals/learning/p39_sources.json`
- `tests/test_runbook_learning_loop.py`
- `tests/test_p39_release_evidence.py`
- `/tmp/opscat-runbook-learning-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_runbook_learning_loop.py tests/test_p39_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.52%; `app/services/runbook_learning_loop.py` coverage 89.32%; P39 runbook learning loop smoke wrote `/tmp/opscat-runbook-learning-loop-latest.md` with 5 source phases, 5 recommendations, 4 regression cases, source coverage 1.0, unsafe learning count 0, and applied change count 0.

Boundary: local learning recommendations only; no automatic production runbook edits; no auth/session work; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.

## P40 Production-readiness Milestone Bundle Evidence

P40 packages P33-P39 evidence into one readiness bundle. It proves local portfolio readiness and explicitly does not claim unattended production operation or production autopilot readiness.

Artifacts:

- `docs/operations/p40-ticket-roadmap.md`
- `docs/operations/p40-final-summary.md`
- `app/services/production_readiness_milestone.py`
- `scripts/run_production_readiness_milestone.py`
- `evals/readiness/p40_sources.json`
- `tests/test_production_readiness_milestone.py`
- `tests/test_p40_release_evidence.py`
- `/tmp/opscat-production-readiness-milestone-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_production_readiness_milestone.py tests/test_p40_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.61%; `app/services/production_readiness_milestone.py` coverage 88.37%; P40 production-readiness milestone smoke wrote `/tmp/opscat-production-readiness-milestone-latest.md` with 8 gates, 8 passed gates, 0 failed gates, boundary violation count 0, production blocker count 3, readiness decision local-portfolio-ready, and production autopilot ready false.

Boundary: local readiness bundle only; does not claim unattended production operation; does not enable production autopilot; no auth/session work; no live API calls; no default external model/API calls during verification; no committed or printed keys; no production mutation; no remediation execution.

## P41 Raw Real Dataset Scored Replay Evidence

P41 evaluates source-native repo-local raw dataset files and scores deterministic incident predictions against labels/root causes without downloading external datasets during verification.

Artifacts:

- `docs/operations/p41-ticket-roadmap.md`
- `docs/operations/p41-final-summary.md`
- `app/services/raw_real_dataset_replay.py`
- `scripts/run_raw_real_dataset_replay.py`
- `evals/real_datasets/raw/p41_sources.json`
- `tests/test_raw_real_dataset_replay.py`
- `tests/test_p41_release_evidence.py`
- `/tmp/opscat-raw-real-dataset-replay-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_raw_real_dataset_replay.py tests/test_p41_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.68%; `app/services/raw_real_dataset_replay.py` coverage 84.15%; P41 raw real dataset replay smoke wrote `/tmp/opscat-raw-real-dataset-replay-latest.md` with raw source count 3, parsed record count 8, label coverage 1.0, root-cause accuracy 1.0, route accuracy 1.0, unsafe action count 0, live API call count 0, download count 0, and passed=true.

Boundary: repo-local raw dataset files only; no external dataset downloads during verification; no live API calls; no auth/session work; no default external model/API calls; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.
## P42 External Dataset Acquisition & Holdout Evaluation Evidence

P42 adds an opt-in acquisition plan for public external datasets and a deterministic holdout evaluation path. Normal verification remains local and does not download external datasets.

Artifacts:

- `docs/operations/p42-ticket-roadmap.md`
- `docs/operations/p42-final-summary.md`
- `evals/real_datasets/external/p42_manifest.json`
- `app/services/external_dataset_acquisition.py`
- `scripts/prepare_external_datasets.py`
- `tests/test_external_dataset_acquisition.py`
- `tests/test_p42_release_evidence.py`
- `/tmp/opscat-external-dataset-acquisition-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_external_dataset_acquisition.py tests/test_p42_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 78.77%; `app/services/external_dataset_acquisition.py` coverage 85.17%; P42 external dataset acquisition smoke wrote `/tmp/opscat-external-dataset-acquisition-latest.md` with source count 3, dry-run download count 0, holdout source count 2, holdout parsed record count 4, label coverage 1.0, root-cause accuracy 1.0, route accuracy 1.0, unsafe action count 0, boundary violation count 0, network_allowed=false, external_downloads_performed=false, and passed=true.

Boundary: default dry-run only; no external dataset downloads during verification; no live API calls; no auth/session work; no default external model/API calls; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.
## P43 Opt-in Public Dataset Download & Benchmark Scorecard Evidence

P43 downloads small public LogHub/NAB samples only when explicitly allowed, materializes them into P41 raw replay format, and scores them. Normal verification remains offline and fixture-backed.

Artifacts:

- `docs/operations/p43-ticket-roadmap.md`
- `docs/operations/p43-final-summary.md`
- `evals/real_datasets/external/p43_public_benchmark_manifest.json`
- `app/services/public_dataset_benchmark.py`
- `scripts/run_public_dataset_benchmark.py`
- `tests/test_public_dataset_benchmark.py`
- `tests/test_p43_release_evidence.py`
- `/tmp/opscat-public-dataset-benchmark-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_public_dataset_benchmark.py tests/test_p43_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`
- `python3 scripts/run_public_dataset_benchmark.py --allow-network --manifest evals/real_datasets/external/p43_public_benchmark_manifest.json --output-json /tmp/opscat-public-dataset-benchmark-live.json --output-md /tmp/opscat-public-dataset-benchmark-live.md`

Verified result: full profile passed; coverage gate 78.90%; `app/services/public_dataset_benchmark.py` coverage 84.99%; P43 offline smoke wrote `/tmp/opscat-public-dataset-benchmark-latest.md` with dataset_mode=fixture_fallback, source count 2, download count 0, parsed record count 7, root-cause accuracy 1.0, route accuracy 1.0, network_allowed=false, and external_downloads_performed=false. Explicit opt-in public download benchmark wrote `/tmp/opscat-public-dataset-benchmark-live.md` with dataset_mode=downloaded_public_sample, download count 3, downloaded bytes 918821, materialized source count 2, parsed record count 4000, label coverage 1.0, root-cause accuracy 1.0, route accuracy 1.0, unsafe action count 0, network_allowed=true, external_downloads_performed=true, generated_artifacts_committed=false, and passed=true.

Boundary: default offline fixture fallback; public downloads require explicit opt-in; generated dataset artifacts are not committed; no live API calls; no auth/session work; no default external model/API calls; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.
## P44 Larger Public Dataset Benchmark Matrix Evidence

P44 expands public benchmark evidence into a multi-source matrix with source-level and family-level scores. Normal verification remains offline and fixture-backed; public downloads require explicit opt-in.

Artifacts:

- `docs/operations/p44-ticket-roadmap.md`
- `docs/operations/p44-final-summary.md`
- `evals/real_datasets/external/p44_benchmark_matrix_manifest.json`
- `app/services/public_dataset_matrix.py`
- `scripts/run_public_dataset_matrix.py`
- `tests/test_public_dataset_matrix.py`
- `tests/test_p44_release_evidence.py`
- `/tmp/opscat-public-dataset-matrix-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_public_dataset_matrix.py tests/test_p44_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`
- `python3 scripts/run_public_dataset_matrix.py --allow-network --manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json --output-json /tmp/opscat-public-dataset-matrix-live.json --output-md /tmp/opscat-public-dataset-matrix-live.md`

Verified result: full profile passed; coverage gate 78.99%; `app/services/public_dataset_matrix.py` coverage 87.62%; P44 offline matrix smoke wrote `/tmp/opscat-public-dataset-matrix-latest.md` with dataset_mode=fixture_fallback, source count 5, download count 0, matrix row count 5, family count 2, parsed record count 18, root-cause accuracy 1.0, route accuracy 1.0, network_allowed=false, and external_downloads_performed=false. Explicit opt-in public matrix wrote `/tmp/opscat-public-dataset-matrix-live.md` with dataset_mode=downloaded_public_sample, source count 5, download count 8, matrix row count 5, family count 2, parsed record count 10000, label coverage 1.0, root-cause accuracy 1.0, route accuracy 1.0, unsafe action count 0, false-positive proxy count 0, false-negative proxy count 0, worst_sources=[], network_allowed=true, external_downloads_performed=true, generated_artifacts_committed=false, and passed=true.

Boundary: default offline fixture fallback; public downloads require explicit opt-in; generated dataset artifacts are not committed; no live API calls; no auth/session work; no default external model/API calls; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.
## P45 Evidence-Grounded Judgment Contract Evidence

P45 enforces evidence-grounded incident judgments with support, counter-evidence, missing evidence, confidence, uncertainty, and action boundaries.

Artifacts:

- `docs/operations/p45-ticket-roadmap.md`
- `docs/operations/p45-final-summary.md`
- `evals/investigator/p45_judgment_cases.json`
- `app/services/evidence_grounded_judgment.py`
- `scripts/run_evidence_grounded_judgment.py`
- `tests/test_evidence_grounded_judgment.py`
- `tests/test_p45_release_evidence.py`
- `/tmp/opscat-evidence-grounded-judgment-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_evidence_grounded_judgment.py tests/test_p45_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.31%; P45 smoke wrote `/tmp/opscat-evidence-grounded-judgment-latest.md` with case_count=3, valid_contract_count=3, grounded_ratio=1.0, conservative_route_count=3, unsafe_auto_execute_count=0, and passed=true.

Boundary: offline fixtures only; no live API calls; no auth/session work; no default external model/API calls; no committed or printed keys; no production mutation; no remediation execution; does not claim unattended production operation.
## P46 Investigator Loop Evidence

P46 adds an operator-like loop that turns observed signals into ranked hypotheses, evidence bindings, missing evidence, next investigations, and conservative action gates.

Artifacts:

- `docs/operations/p46-ticket-roadmap.md`
- `docs/operations/p46-final-summary.md`
- `evals/investigator/p46_investigation_cases.json`
- `app/services/investigator_loop.py`
- `scripts/run_investigator_loop.py`
- `tests/test_investigator_loop.py`
- `tests/test_p46_release_evidence.py`
- `/tmp/opscat-investigator-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_investigator_loop.py tests/test_p46_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.31%; P46 smoke wrote `/tmp/opscat-investigator-loop-latest.md` with incident_count=2, hypothesis_count=10, grounded_hypothesis_ratio=1.0, top_hypothesis_match_ratio=1.0, unsafe_action_count=0, and passed=true.

Boundary: offline fixtures only; read-only investigation planning; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.
## P47 Tool Selection Planner Evidence

P47 maps investigation requests to safe read-only tool plans and blocks mutation/shell/remediation tools.

Artifacts:

- `docs/operations/p47-ticket-roadmap.md`
- `docs/operations/p47-final-summary.md`
- `evals/investigator/p47_tool_selection_cases.json`
- `app/services/tool_selection_planner.py`
- `scripts/run_tool_selection_planner.py`
- `tests/test_tool_selection_planner.py`
- `tests/test_p47_release_evidence.py`
- `/tmp/opscat-tool-selection-planner-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_tool_selection_planner.py tests/test_p47_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.31%; P47 smoke wrote `/tmp/opscat-tool-selection-planner-latest.md` with case_count=3, selected_tool_count=6, blocked_tool_count=3, read_only_ratio=1.0, unsafe_selected_count=0, and passed=true.

Boundary: offline tool planning only; no live API calls; no auth/session work; no default external model/API calls; no production mutation; no remediation execution; no unrestricted shell; does not claim unattended production operation.
## P48 Hypothesis Re-ranking Evidence

P48 updates hypothesis rankings after read-only investigation results arrive, records anti-anchoring demotions, and keeps action gates conservative.

Artifacts:

- `docs/operations/p48-ticket-roadmap.md`
- `docs/operations/p48-final-summary.md`
- `evals/investigator/p48_rerank_cases.json`
- `app/services/hypothesis_reranker.py`
- `scripts/run_hypothesis_reranker.py`
- `tests/test_hypothesis_reranker.py`
- `tests/test_p48_release_evidence.py`
- `/tmp/opscat-hypothesis-reranker-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_hypothesis_reranker.py tests/test_p48_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.31%; P48 smoke wrote `/tmp/opscat-hypothesis-reranker-latest.md` with case_count=2, expected_top_match_count=2, expected_top_match_ratio=1.0, anti_anchoring_demotions=1, unsafe_action_count=0, and passed=true.

Boundary: offline read-only investigation results only; no live API calls; no auth/session work; no default external model/API calls; no production mutation; no remediation execution; does not claim unattended production operation.

## P49 Remediation Verification Loop Evidence

P49 verifies proposed remediations through pre-checks, mock/draft execution boundaries, post-checks, and recovery-or-escalation routing.

Artifacts:

- `docs/operations/p49-ticket-roadmap.md`
- `docs/operations/p49-final-summary.md`
- `evals/investigator/p49_remediation_verification_cases.json`
- `app/services/remediation_verification_loop.py`
- `scripts/run_remediation_verification_loop.py`
- `tests/test_remediation_verification_loop.py`
- `tests/test_p49_release_evidence.py`
- `/tmp/opscat-remediation-verification-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_remediation_verification_loop.py tests/test_p49_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.31%; P49 smoke wrote `/tmp/opscat-remediation-verification-loop-latest.md` with case_count=2, precheck_pass_count=2, recovery_verified_count=1, failed_verification_escalation_count=1, production_execution_count=0, unsafe_action_count=0, and passed=true.

Boundary: offline fixtures only; mock/draft remediation boundary only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P50 Night Operator Drill v2 Evidence

P50 chains P45-P49 local evidence into a night-operator drill that can watch locally but does not claim unattended production readiness.

Artifacts:

- `docs/operations/p50-ticket-roadmap.md`
- `docs/operations/p50-final-summary.md`
- `evals/investigator/p50_night_operator_cases.json`
- `app/services/night_operator_drill_v2.py`
- `scripts/run_night_operator_drill_v2.py`
- `tests/test_night_operator_drill_v2.py`
- `tests/test_p50_release_evidence.py`
- `/tmp/opscat-night-operator-drill-v2-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_night_operator_drill_v2.py tests/test_p50_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.31%; P50 smoke wrote `/tmp/opscat-night-operator-drill-v2-latest.md` with drill_count=2, evidence_contract_pass_count=2, investigation_complete_count=2, read_only_tool_plan_count=6, remediation_verification_count=2, production_execution_count=0, unsafe_auto_execute_count=0, local_night_watch_ready=true, unattended_production_ready=false, and passed=true.

Boundary: offline fixtures only; read-only/mocked local drill only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P51 Operator Judgment Benchmark v2 Evidence

P51 scores operator judgment quality before additional UI or live-product integration work.

Artifacts:

- `docs/operations/p51-ticket-roadmap.md`
- `docs/operations/p51-final-summary.md`
- `evals/investigator/p51_operator_judgment_benchmark_v2_cases.json`
- `app/services/operator_judgment_benchmark_v2.py`
- `scripts/run_operator_judgment_benchmark_v2.py`
- `tests/test_operator_judgment_benchmark_v2.py`
- `tests/test_p51_release_evidence.py`
- `/tmp/opscat-operator-judgment-benchmark-v2-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_judgment_benchmark_v2.py tests/test_p51_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.36%; P51 smoke wrote `/tmp/opscat-operator-judgment-benchmark-v2-latest.md` with case_count=4, detection_recall=1.0, top1_hypothesis_accuracy=1.0, evidence_quality_score=0.938, route_accuracy=1.0, rerank_success_rate=1.0, recovery_verification_coverage=0.5, unsafe_auto_execute_count=0, production_execution_count=0, live_call_count=0, evidence_gap=1, recovery_verification_gap=2, and passed=true.

Boundary: offline benchmark fixtures only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P52 Failure Mining Loop Evidence

P52 converts P51 benchmark failures into prioritized improvement tickets and regression cases.

Artifacts:

- `docs/operations/p52-ticket-roadmap.md`
- `docs/operations/p52-final-summary.md`
- `app/services/failure_mining_loop.py`
- `scripts/run_failure_mining_loop.py`
- `tests/test_failure_mining_loop.py`
- `tests/test_p52_release_evidence.py`
- `/tmp/opscat-failure-mining-loop-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_failure_mining_loop.py tests/test_p52_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.43%; P52 smoke wrote `/tmp/opscat-failure-mining-loop-latest.md` with source_case_count=4, failure_cluster_count=2, improvement_ticket_count=2, regression_case_count=3, highest_priority=P1, unsafe_action_count=0, evidence_gap cluster count=1, recovery_verification_gap cluster count=2, and passed=true.

Boundary: offline P51 benchmark mining only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P53 Failure-Driven Improvement Pack Evidence

P53 turns P52 mined gaps into concrete evidence probes, recovery checks, regression cases, and validation commands.

Artifacts:

- `docs/operations/p53-ticket-roadmap.md`
- `docs/operations/p53-final-summary.md`
- `app/services/failure_driven_improvement_pack.py`
- `scripts/run_failure_driven_improvement_pack.py`
- `tests/test_failure_driven_improvement_pack.py`
- `tests/test_p53_release_evidence.py`
- `/tmp/opscat-failure-driven-improvement-pack-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_failure_driven_improvement_pack.py tests/test_p53_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.43%; P53 smoke wrote `/tmp/opscat-failure-driven-improvement-pack-latest.md` with source_failure_cluster_count=2, improvement_plan_count=2, evidence_probe_count=5, recovery_check_count=5, regression_case_count=3, unsafe_action_count=0, projected evidence_gap 1→0, projected recovery_verification_gap 2→0, and passed=true.

Boundary: offline P52 improvement planning only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P54 Failure-Driven Benchmark Improvement Evidence

P54 applies the P53 improvement pack to a derived P51 benchmark view and proves the mined evidence/recovery gaps close without mutating the baseline fixture.

Artifacts:

- `docs/operations/p54-ticket-roadmap.md`
- `docs/operations/p54-final-summary.md`
- `app/services/failure_driven_benchmark_improvement.py`
- `scripts/run_failure_driven_benchmark_improvement.py`
- `tests/test_failure_driven_benchmark_improvement.py`
- `tests/test_p54_release_evidence.py`
- `/tmp/opscat-failure-driven-benchmark-improvement-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_failure_driven_benchmark_improvement.py tests/test_p54_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.49%; P54 smoke wrote `/tmp/opscat-failure-driven-benchmark-improvement-latest.md` with case_count=4, applied_improvement_count=3, improved_case_count=2, baseline_preserved=true, baseline evidence_gap=1, improved evidence_gap=0, baseline recovery_verification_gap=2, improved recovery_verification_gap=0, evidence_quality_score_delta=0.062, recovery_verification_coverage_delta=0.5, unsafe_action_count=0, and passed=true.

Boundary: offline derived benchmark view only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P55 Candidate Benchmark Promotion Gate Evidence

P55 promotes the P54 improved derived benchmark view into a versioned candidate benchmark pack while preserving the P51 fixture as the immutable regression baseline.

Artifacts:

- `docs/operations/p55-ticket-roadmap.md`
- `docs/operations/p55-final-summary.md`
- `app/services/candidate_benchmark_promotion_gate.py`
- `scripts/run_candidate_benchmark_promotion_gate.py`
- `tests/test_candidate_benchmark_promotion_gate.py`
- `tests/test_p55_release_evidence.py`
- `/tmp/opscat-candidate-benchmark-promotion-gate-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_candidate_benchmark_promotion_gate.py tests/test_p55_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.50%; P55 smoke wrote `/tmp/opscat-candidate-benchmark-promotion-gate-latest.md` with source_case_count=4, candidate_case_count=4, improved_case_count=2, promotion_status=candidate_ready, baseline_release_status=preserved_reference_only, promotion_gate_count=5, evidence_gap=1→0, recovery_verification_gap=2→0, evidence_quality_score_delta=0.062, recovery_verification_coverage_delta=0.5, unsafe_action_count=0, source_fingerprint_sha256=de893219300f73aa879403aa5e0c456ddfcc0cca9694a6e40db929bf98e253ee, candidate_fingerprint_sha256=3ebf8f5ce76ce5467eb17bb5ac3fb5403783defbaea969c00f82ba743b4b8bf7, and passed=true.

Boundary: offline candidate benchmark only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P56 Candidate Benchmark Regression Runner Evidence

P56 repeats the P55 promotion gate to prove the candidate benchmark is stable, non-regressing, and safe across repeated local runs.

Artifacts:

- `docs/operations/p56-ticket-roadmap.md`
- `docs/operations/p56-final-summary.md`
- `app/services/candidate_benchmark_regression_runner.py`
- `scripts/run_candidate_benchmark_regression_runner.py`
- `tests/test_candidate_benchmark_regression_runner.py`
- `tests/test_p56_release_evidence.py`
- `/tmp/opscat-candidate-benchmark-regression-runner-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_candidate_benchmark_regression_runner.py tests/test_p56_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.63%; P56 smoke wrote `/tmp/opscat-candidate-benchmark-regression-runner-latest.md` with repeat_count=3, stable_source_fingerprint=true, stable_candidate_fingerprint=true, source_fingerprint_unique_count=1, candidate_fingerprint_unique_count=1, all_gap_closures_stable=true, all_score_deltas_non_negative=true, unsafe_action_count=0, and passed=true.

Boundary: offline candidate regression gate only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P57 Real Dataset Candidate Regression Bridge Evidence

P57 links P56 candidate benchmark regression with the P44 public real-dataset matrix in offline fixture fallback mode.

Artifacts:

- `docs/operations/p57-ticket-roadmap.md`
- `docs/operations/p57-final-summary.md`
- `app/services/real_dataset_candidate_regression_bridge.py`
- `scripts/run_real_dataset_candidate_regression_bridge.py`
- `tests/test_real_dataset_candidate_regression_bridge.py`
- `tests/test_p57_release_evidence.py`
- `/tmp/opscat-real-dataset-candidate-regression-bridge-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_real_dataset_candidate_regression_bridge.py tests/test_p57_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.63%; P57 smoke wrote `/tmp/opscat-real-dataset-candidate-regression-bridge-latest.md` with candidate_regression_passed=true, dataset_matrix_passed=true, dataset_mode=fixture_fallback, dataset_source_count=5, dataset_family_count=2, parsed_record_count=18, root_cause_accuracy=1.0, route_accuracy=1.0, label_coverage=1.0, worst_sources=0, unsafe_action_count=0, and passed=true.

Boundary: offline real-dataset bridge only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; does not claim unattended production operation.

## P58 LLM Judgment Candidate Harness Evidence

P58 evaluates the local/mock LLM judgment lane behind P57 bridge gates so model quality is measured against candidate and real-dataset evidence before external providers are used.

Artifacts:

- `docs/operations/p58-ticket-roadmap.md`
- `docs/operations/p58-final-summary.md`
- `app/services/llm_judgment_candidate_harness.py`
- `scripts/run_llm_judgment_candidate_harness.py`
- `tests/test_llm_judgment_candidate_harness.py`
- `tests/test_p58_release_evidence.py`
- `/tmp/opscat-llm-judgment-candidate-harness-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_judgment_candidate_harness.py tests/test_p58_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.63%; P58 smoke wrote `/tmp/opscat-llm-judgment-candidate-harness-latest.md` with bridge_passed=true, provider=mock, model=mock, llm_case_count=4, llm_pass_rate=1.0, llm_overall_score=0.964, schema_average=1.0, citation_average=1.0, safety_average=1.0, safety_regression_count=0, failed_case_count=0, and passed=true.

Boundary: offline mock LLM harness only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.

## P59 Hybrid Commander Comparator Evidence

P59 compares deterministic candidate gates, local/mock LLM judgment, and a guarded hybrid commander lane under one safety-preserving scorecard.

Artifacts:

- `docs/operations/p59-ticket-roadmap.md`
- `docs/operations/p59-final-summary.md`
- `app/services/hybrid_commander_comparator.py`
- `scripts/run_hybrid_commander_comparator.py`
- `tests/test_hybrid_commander_comparator.py`
- `tests/test_p59_release_evidence.py`
- `/tmp/opscat-hybrid-commander-comparator-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_hybrid_commander_comparator.py tests/test_p59_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.63%; P59 smoke wrote `/tmp/opscat-hybrid-commander-comparator-latest.md` with harness_passed=true, lane_count=3, recommended_lane=hybrid_guarded, deterministic_score=1.0, llm_mock_score=0.964, hybrid_guarded_score=1.0, safety_regression_count=0, action_execution_count=0, and passed=true.

Boundary: offline hybrid comparator only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.

## P60 Operator Replacement Readiness Gate v2 Evidence

P60 aggregates P56-P59 evidence into local/shadow operator replacement readiness while explicitly blocking unattended production autonomy.

Artifacts:

- `docs/operations/p60-ticket-roadmap.md`
- `docs/operations/p60-final-summary.md`
- `app/services/operator_replacement_readiness_gate_v2.py`
- `scripts/run_operator_replacement_readiness_gate_v2.py`
- `tests/test_operator_replacement_readiness_gate_v2.py`
- `tests/test_p60_release_evidence.py`
- `/tmp/opscat-operator-replacement-readiness-gate-v2-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_replacement_readiness_gate_v2.py tests/test_p60_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.63%; P60 smoke wrote `/tmp/opscat-operator-replacement-readiness-gate-v2-latest.md` with hybrid_comparator_passed=true, local_operator_replacement_ready=true, unattended_production_ready=false, recommended_mode=local_shadow_operator_replacement, readiness_level=shadow_ready_production_blocked, safety_regression_count=0, action_execution_count=0, production_blockers=5, and passed=true.

Boundary: offline operator replacement readiness gate only; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.

## P61 Local Shadow Connector Validation Evidence

P61 validates a live-shaped local observability source through a read-only connector contract before any real server or staging connector is used.

Artifacts:

- `docs/operations/p61-ticket-roadmap.md`
- `docs/operations/p61-final-summary.md`
- `evals/shadow/p61_local_shadow_source.json`
- `app/services/local_shadow_connector_validation.py`
- `scripts/run_local_shadow_connector_validation.py`
- `tests/test_local_shadow_connector_validation.py`
- `tests/test_p61_release_evidence.py`
- `/tmp/opscat-local-shadow-connector-validation-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_local_shadow_connector_validation.py tests/test_p61_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.72%; P61 smoke wrote `/tmp/opscat-local-shadow-connector-validation-latest.md` with source_count=3, metric_signal_count=2, log_signal_count=2, error_signal_count=1, deployment_signal_count=1, empty_source_count=1, malformed_payload_count=1, supporting_evidence_count=4, counter_evidence_count=2, missing_evidence_count=2, top_hypothesis=recent_deploy_regression, confidence=0.91, recommended_action=prepare rollback PR draft, execution=blocked_shadow_mode, local_operator_replacement_ready=true, unattended_production_ready=false, action_execution_count=0, live_api_call_count=0, production_mutation_count=0, validation_gate_count=6, and passed=true.

Boundary: offline local shadow connector only; no real server connection; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.

## P62 Staging Read-only Connector Contract Evidence

P62 validates provider-shaped staging connector contracts for Grafana, Sentry, and Datadog before any real staging API credentials or network calls are used.

Artifacts:

- `docs/operations/p62-ticket-roadmap.md`
- `docs/operations/p62-final-summary.md`
- `evals/staging/p62_staging_connector_contract.json`
- `app/services/staging_read_only_connector_contract.py`
- `scripts/run_staging_read_only_connector_contract.py`
- `tests/test_staging_read_only_connector_contract.py`
- `tests/test_p62_release_evidence.py`
- `/tmp/opscat-staging-read-only-connector-contract-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_staging_read_only_connector_contract.py tests/test_p62_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.84%; P62 smoke wrote `/tmp/opscat-staging-read-only-connector-contract-latest.md` with connector_count=4, ready_count=3, degraded_count=0, blocked_count=1, provider_count=3, schema_compatible_count=3, provider_coverage_rate=1.0, read_only_safety_rate=0.75, staging_environment_rate=0.75, schema_compatibility_rate=0.75, ready_connectors=p62-grafana-staging/p62-sentry-staging/p62-datadog-staging, blocked_connectors=p62-prod-admin-blocked, next_step="attach staging read-only credentials behind manual approval", action_execution_count=0, live_api_call_count=0, production_mutation_count=0, and passed=true.

Boundary: offline staging connector contract only; local manifest and sample responses only; no real server connection; no live API calls; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.

## P63 Staging Live Read-only Preflight Evidence

P63 adds the final preflight gate before staging observability APIs can be contacted. Default mode evaluates eligibility and performs zero API calls; live-path behavior is verified with an injected mock transport only.

Artifacts:

- `docs/operations/p63-ticket-roadmap.md`
- `docs/operations/p63-final-summary.md`
- `evals/staging/p63_staging_live_preflight.json`
- `app/services/staging_live_read_only_preflight.py`
- `scripts/run_staging_live_read_only_preflight.py`
- `tests/test_staging_live_read_only_preflight.py`
- `tests/test_p63_release_evidence.py`
- `/tmp/opscat-staging-live-read-only-preflight-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_staging_live_read_only_preflight.py tests/test_p63_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: full profile passed; coverage gate 79.91%; P63 smoke wrote `/tmp/opscat-staging-live-read-only-preflight-latest.md` with check_count=4, eligible_check_count=3, attempted_check_count=0, successful_check_count=0, blocked_check_count=1, non_get_check_count=1, manual_approval_missing_count=0, mock_transport_call_count=0, live_api_call_count=0, action_execution_count=0, production_mutation_count=0, eligible_checks=p63-grafana-health-get/p63-sentry-projects-get/p63-datadog-monitors-get, blocked_checks=p63-prod-admin-post-blocked, next_step="rerun with explicit live staging flag after manual approval and read-only credentials", and passed=true.

Boundary: default no-live staging preflight only; no real server connection in normal verification; live path requires explicit live staging gates; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.

## P64 Audited Staging Credential + Transport Gate Evidence

P64 adds an audited credential and transport gate between P63 preflight eligibility and any network-capable staging transport. Default mode records audit decisions and performs zero transport calls.

Artifacts:

- `docs/operations/p64-ticket-roadmap.md`
- `docs/operations/p64-final-summary.md`
- `evals/staging/p64_audited_credential_transport_gate.json`
- `app/services/audited_staging_transport_gate.py`
- `scripts/run_audited_staging_transport_gate.py`
- `tests/test_audited_staging_transport_gate.py`
- `tests/test_p64_release_evidence.py`
- `/tmp/opscat-audited-staging-transport-gate-latest.md`

Verification:

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_audited_staging_transport_gate.py tests/test_p64_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

Verified result: pending final full profile.

Boundary: default dry-run audited staging transport gate only; injected mock secret store only; no `.env` reads; no real credentials; no real server connection in normal verification; no auth/session work; no production mutation; no remediation execution; no default external model/API calls; no action execution; does not claim unattended production operation.
