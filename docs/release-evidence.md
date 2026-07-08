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
