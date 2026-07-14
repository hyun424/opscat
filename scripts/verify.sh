#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERIFY_PROFILE="full"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      VERIFY_PROFILE="${2:-}"
      shift 2
      ;;
    --profile=*)
      VERIFY_PROFILE="${1#--profile=}"
      shift
      ;;
    -h|--help)
      cat <<'HELP'
Usage: bash scripts/verify.sh [--profile fast|full|eval|docs|p107-release|...|p140-release]

Profiles:
  fast  Compile, lint, typecheck, and pytest regression suite.
  full  Complete release gate, including coverage, evals, demos, Docker config, and hygiene checks.
  eval  Golden incident evals, connector evals, and P6 agentic-loop evals only.
  docs  Documentation/release evidence contract tests plus repo hygiene checks.
  p107-release
        P107 local/mock/isolated release profile tests plus canary evidence smoke.
  p108-release
        P108 deterministic offline learning profile tests plus evidence smoke.
  p109-release
        P109 offline external-evidence import, benchmark, authority, and release tests.
  p110-release
        P110 labeled RCAEval import, blind LLM runner, scoring, and release tests.
  p111-release
        P111 evidence digest, benchmark governance, paired scoring, and P110 compatibility tests.
  p112-release
        P112 cross-system model, paired freeze, replay, scoring, and release tests.
  p113-release
        P113 fresh-blind diagnosis/narrative separation, governance, and release tests.
  p114-release
        P114 consumed-lineage, RE2 acquisition, evidence graph, and adjudication tests.
  p115-release
        P115 outcome-grounded action contracts, ontology, matrices, baselines, and scoring.
  p116-release
        P116 controlled five-arm loopback lab and paired measured-outcome contracts.
  p117-release
        P117 frozen evidence-bound action-selection tournament and release evidence.
  p118-release
        P118 fail-closed local/mock/sandbox reactive execution substrate and release evidence.
  p119-release
        P119 local/mock/sandbox closed-loop incident response and release evidence.
  p120-release
        P120 frozen cross-system generalization benchmark and release evidence.
  p121-release
        P121 local/mock/sandbox proactive prevention and release evidence.
  p122-release
        P122 open-source packaging, security, reproducibility, and bounded release evidence.
  p123-release..p133-release
        Evidence-qualified shadow attachment, judgment, resilience, local lab,
        chaos, operator UX, distribution, and public-beta release profiles.
  p134-release
        Observation-authority policy contract, immutable receipts, independent review, and release evidence.
  p135-release
        Credential-free provider-shaped local export attachment, normalization, ledgers, and release evidence.
  p136-release
        Crash-safe incremental local observation, real P135 bridge, recovery, and source-bound release evidence.
  p137-release
        Local-only evidence-to-incident triage, bounded investigation, crash recovery, and source-bound release evidence.
  p138-release
        Frozen 30-case observation-to-triage supervision, independent review, and source-bound release evidence.
  p139-release
        Hardened local process host, restart recovery, exact 32-case matrix, and source-bound release evidence.
  p140-release
        Credential-free P139 health adapter, P133 dead-man outbox, exact 32-case matrix, and source-bound release evidence.
HELP
      exit 0
      ;;
    *)
      printf 'Unknown verify argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

case "$VERIFY_PROFILE" in
  fast|full|eval|docs|p107-release|p108-release|p109-release|p110-release|p111-release|p112-release|p113-release|p114-release|p115-release|p116-release|p117-release|p118-release|p119-release|p120-release|p121-release|p122-release|p123-release|p124-release|p125-release|p126-release|p127-release|p128-release|p129-release|p130-release|p131-release|p132-release|p133-release|p134-release|p135-release|p136-release|p137-release|p138-release|p139-release|p140-release) ;;
  *)
    printf 'Unknown verify profile: %s\n' "$VERIFY_PROFILE" >&2
    exit 2
    ;;
esac

section() {
  printf '\n==> %s\n' "$1"
}

UV_DEV=(uv run --no-sync --extra dev)
P107_RELEASE_PROFILE_TESTS=(
  tests/test_prevention_p106_handoff.py
  tests/test_prevention_canary_fingerprints.py
  tests/test_prevention_policy_preflight.py
  tests/test_prevention_state_machine.py
  tests/test_prevention_episode_audit.py
  tests/test_prevention_canary_harness.py
  tests/test_prevention_canary_executor_contract.py
  tests/test_prevention_canary_idempotency.py
  tests/test_prevention_canary_concurrency.py
  tests/test_prevention_canary_crash_consistency.py
  tests/test_prevention_canary_rollback.py
  tests/test_prevention_canary_fixture_matrix.py
  tests/test_prevention_outcome_report.py
  tests/test_prevention_static_authority_boundary.py
  tests/test_p107_release_evidence.py
)
P108_RELEASE_PROFILE_TESTS=(
  tests/test_prevention_p108_ingress.py
  tests/test_prevention_replay_gate.py
  tests/test_prevention_outcome_ledger.py
  tests/test_prevention_counterfactual.py
  tests/test_prevention_outcome_learner.py
  tests/test_prevention_learning_recommendations.py
  tests/test_prevention_learning_promotion.py
  tests/test_prevention_p108_fixture_matrix.py
  tests/test_prevention_p108_authority_boundary.py
  tests/test_prevention_learning_cli.py
  tests/test_p108_release_evidence.py
)
P109_RELEASE_PROFILE_TESTS=(
  tests/test_p109_source_manifest.py
  tests/test_p109_safe_acquisition.py
  tests/test_rcaeval_adapter.py
  tests/test_rcaeval_diagnosis_benchmark.py
  tests/test_microremed_result_adapter.py
  tests/test_remediation_outcome_benchmark_p109.py
  tests/test_p109_holdout_guard.py
  tests/test_p109_release_evidence.py
  tests/test_p109_authority_boundary.py
  tests/test_p109_real_sample_smoke.py
)
P110_RELEASE_PROFILE_TESTS=(
  tests/test_p110_acquisition.py
  tests/test_p110_rcaeval.py
  tests/test_p110_candidate_runner.py
  tests/test_p110_evaluation.py
  tests/test_p110_release_evidence.py
  tests/test_p110_batch_merge.py
)
P111_RELEASE_PROFILE_TESTS=(
  "${P110_RELEASE_PROFILE_TESTS[@]}"
  tests/test_p111_multistage_rca.py
  tests/test_p111_fault_prior.py
  tests/test_p111_benchmark_guard.py
  tests/test_p111_comparison.py
  tests/test_p111_release_evidence.py
)
P112_RELEASE_PROFILE_TESTS=(
  "${P111_RELEASE_PROFILE_TESTS[@]}"
  tests/test_p112_re1_loader.py
  tests/test_p112_cross_system_model.py
  tests/test_p112_multistage_rca.py
  tests/test_p112_evaluation.py
  tests/test_p112_freeze_guard.py
  tests/test_p112_release_evidence.py
)
P113_RELEASE_PROFILE_TESTS=(
  "${P112_RELEASE_PROFILE_TESTS[@]}"
  tests/test_p113_acquisition.py
  tests/test_p113_benchmark_runtime.py
  tests/test_p113_blind_benchmark.py
  tests/test_p113_blind_dataset.py
  tests/test_p113_decoupled_rca.py
  tests/test_p113_evaluation.py
  tests/test_p113_governance.py
  tests/test_p113_release_evidence.py
)
P114_RELEASE_PROFILE_TESTS=(
  "${P113_RELEASE_PROFILE_TESTS[@]}"
  tests/test_p114_acquisition.py
  tests/test_p114_governance.py
  tests/test_p114_re2_loader.py
  tests/test_p114_hypothesis_lattice.py
  tests/test_p114_development_evaluation.py
  tests/test_p114_development_runner.py
  tests/test_p114_adjudicator.py
  tests/test_p114_paired_evaluation.py
  tests/test_p114_adjudication_development.py
  tests/test_p114_fault_knn.py
  tests/test_p114_acceptance.py
  tests/test_p114_authority_boundary.py
)
P115_RELEASE_PROFILE_TESTS=(
  tests/test_p115_action_contract.py
  tests/test_p115_ontology.py
  tests/test_p115_leakage_guard.py
  tests/test_p115_evaluator.py
  tests/test_p115_scenario_matrix.py
  tests/test_p115_baselines.py
  tests/test_p115_release_evidence.py
  tests/test_p115_p116_benchmark_adapter.py
)
P116_RELEASE_PROFILE_TESTS=(
  tests/test_p116_paired_outcomes.py
  tests/test_p116_lab_runner.py
  tests/test_p116_release_evidence.py
)
P117_RELEASE_PROFILE_TESTS=(
  tests/test_p117_contract.py
  tests/test_p117_evidence_acquisition.py
  tests/test_p117_contradictions.py
  tests/test_p117_utility.py
  tests/test_p117_selector.py
  tests/test_p117_nvidia_proposal.py
  tests/test_p117_evaluator.py
  tests/test_p117_benchmark.py
  tests/test_p117_release_evidence.py
)
P118_RELEASE_PROFILE_TESTS=(
  tests/test_p118_operation_contract.py
  tests/test_p118_action_pack_verifier.py
  tests/test_p118_approval.py
  tests/test_p118_ledger.py
  tests/test_p118_worker.py
  tests/test_p118_validation_cycle.py
  tests/test_p118_crash_recovery.py
  tests/test_p118_evaluator_release_evidence.py
)
P119_RELEASE_PROFILE_TESTS=(
  tests/test_p119_contract.py
  tests/test_p119_ledger.py
  tests/test_p119_scheduler.py
  tests/test_p119_evidence_loop.py
  tests/test_p119_selection.py
  tests/test_p119_execution_loop.py
  tests/test_p119_war_room.py
  tests/test_p119_attribution.py
  tests/test_p119_recovery.py
  tests/test_p119_evaluator_release_evidence.py
)
P120_RELEASE_PROFILE_TESTS=(
  tests/test_p120_governance.py
  tests/test_p120_splits.py
  tests/test_p120_normalization.py
  tests/test_p120_ontology.py
  tests/test_p120_ood.py
  tests/test_p120_calibration.py
  tests/test_p120_evaluator_release_evidence.py
)
P121_RELEASE_PROFILE_TESTS=(
  tests/test_p121_signals.py
  tests/test_p121_forecasting.py
  tests/test_p121_counterfactuals.py
  tests/test_p121_guardrails.py
  tests/test_p121_execution.py
  tests/test_p121_validation.py
  tests/test_p121_evaluator_release_evidence.py
)
P122_RELEASE_PROFILE_TESTS=(
  tests/test_p122_public_contracts.py
  tests/test_p122_ci_contract.py
  tests/test_p122_cli.py
  tests/test_p122_security_gate.py
  tests/test_p122_vulnerability_audit.py
  tests/test_p122_reproducible_sdist.py
  tests/test_p122_reproducible_build.py
  tests/test_p122_clean_install.py
  tests/test_p122_performance_soak.py
  tests/test_p122_migration_compatibility.py
  tests/test_p122_docs_verification.py
  tests/test_p122_release_evidence.py
)
P123_RELEASE_PROFILE_TESTS=(tests/test_p123_shadow_attachment.py)
P124_RELEASE_PROFILE_TESTS=(tests/test_p124_judgment_quality.py)
P125_RELEASE_PROFILE_TESTS=(tests/test_p125_shadow_resilience.py)
P126_RELEASE_PROFILE_TESTS=(tests/test_p126_lab_remediation.py)
P127_RELEASE_PROFILE_TESTS=(tests/test_p127_chaos_validation.py)
P128_RELEASE_PROFILE_TESTS=(tests/test_p128_operator_beta.py tests/test_operator_dashboard_e2e.py)
P129_RELEASE_PROFILE_TESTS=(tests/test_p129_distribution_maturity.py)
P130_RELEASE_PROFILE_TESTS=(tests/test_p130_public_beta.py)
P131_RELEASE_PROFILE_TESTS=(tests/test_p131_always_on_monitor.py tests/test_p131_release_evidence.py)
P132_RELEASE_PROFILE_TESTS=(
  tests/test_p131_always_on_monitor.py
  tests/test_p132_supervised_runtime.py
  tests/test_p132_release_evidence.py
)
P133_RELEASE_PROFILE_TESTS=(
  tests/test_p131_always_on_monitor.py
  tests/test_p132_supervised_runtime.py
  tests/test_p132_release_evidence.py
  tests/test_p133_deadman_outbox.py
  tests/test_p133_release_evidence.py
)
P134_RELEASE_PROFILE_TESTS=(
  tests/test_p134_observation_authority.py
  tests/test_p134_release_evidence.py
  tests/test_p134_runner.py
)
P135_RELEASE_PROFILE_TESTS=(
  tests/test_p135_provider_export_attachment.py
  tests/test_p135_release_evidence.py
  tests/test_p135_runner.py
)
P136_RELEASE_PROFILE_TESTS=(
  tests/test_p136_incremental_observer.py
  tests/test_p136_release_evidence.py
  tests/test_p136_runner.py
)
P137_RELEASE_PROFILE_TESTS=(
  tests/test_p137_contracts.py
  tests/test_p137_p136_handoff.py
  tests/test_p137_correlation.py
  tests/test_p137_hypotheses.py
  tests/test_p137_requests.py
  tests/test_p137_classification.py
  tests/test_p137_ledger.py
  tests/test_p137_runtime.py
  tests/test_p137_authority_boundary.py
  tests/test_p137_release_evidence.py
  tests/test_p137_runner.py
)
P138_RELEASE_PROFILE_TESTS=(
  tests/test_p138_observation_triage_supervisor.py
  tests/test_p138_runner.py
  tests/test_p138_release_evidence.py
)
P139_RELEASE_PROFILE_TESTS=(
  tests/test_p139_local_triage_service.py
  tests/test_p139_service_cli.py
  tests/test_p139_runner.py
  tests/test_p139_release_evidence.py
)
P140_RELEASE_PROFILE_TESTS=(
  tests/test_p140_p139_deadman_adapter.py
  tests/test_p140_deadman_cli.py
  tests/test_p140_runner.py
  tests/test_p140_release_evidence.py
)
VERIFY_TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$VERIFY_TMPDIR"
}
trap cleanup EXIT
mkdir -p "$VERIFY_TMPDIR/reports"
export UV_CACHE_DIR="$VERIFY_TMPDIR/uv-cache"
export DATABASE_URL="sqlite:///$VERIFY_TMPDIR/opscat-verify.db"
export REPORT_DIR="$VERIFY_TMPDIR/reports"

compile_check() {
  section "Python bytecode compile"
  PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q app tests scripts
}

lint_check() {
  section "Ruff lint"
  "${UV_DEV[@]}" ruff check app tests scripts
}

type_check() {
  section "Mypy typecheck"
  "${UV_DEV[@]}" mypy app tests scripts
}

pytest_suite() {
  section "Pytest regression suite"
  "${UV_DEV[@]}" pytest -q
}

coverage_gate() {
  section "Coverage gate"
  "${UV_DEV[@]}" python scripts/coverage_gate.py --json-output "$VERIFY_TMPDIR/coverage-summary.json"
}

golden_evals() {
  section "Golden eval runner"
  "${UV_DEV[@]}" python scripts/run_evals.py \
    --output-json "$VERIFY_TMPDIR/opscat-evals.json" \
    --output-md "$VERIFY_TMPDIR/opscat-evals.md" >/tmp/opscat-evals-latest.md
  printf 'Wrote /tmp/opscat-evals-latest.md and %s/opscat-evals.json\n' "$VERIFY_TMPDIR"
}

connector_evals() {
  section "Connector eval runner"
  "${UV_DEV[@]}" python scripts/run_connector_evals.py \
    --output-json "$VERIFY_TMPDIR/opscat-connector-evals.json" \
    --output-md "$VERIFY_TMPDIR/opscat-connector-evals.md" >/tmp/opscat-connector-evals-latest.md
  printf 'Wrote /tmp/opscat-connector-evals-latest.md and %s/opscat-connector-evals.json\n' "$VERIFY_TMPDIR"
}

agentic_evals() {
  section "Agentic eval runner"
  "${UV_DEV[@]}" python scripts/run_agentic_evals.py \
    --output-json "$VERIFY_TMPDIR/opscat-agentic-evals.json" \
    --output-md "$VERIFY_TMPDIR/opscat-agentic-evals.md" >/tmp/opscat-agentic-evals-latest.md
  printf 'Wrote /tmp/opscat-agentic-evals-latest.md and %s/opscat-agentic-evals.json\n' "$VERIFY_TMPDIR"
}

judgment_benchmark() {
  section "P10 judgment benchmark"
  "${UV_DEV[@]}" python scripts/run_judgment_benchmark.py \
    --output-json "$VERIFY_TMPDIR/opscat-judgment-benchmark.json" \
    --output-md "$VERIFY_TMPDIR/opscat-judgment-benchmark.md" >/tmp/opscat-judgment-benchmark-latest.json
  cp "$VERIFY_TMPDIR/opscat-judgment-benchmark.md" /tmp/opscat-judgment-benchmark-latest.md
  printf 'Wrote /tmp/opscat-judgment-benchmark-latest.md and %s/opscat-judgment-benchmark.json\n' "$VERIFY_TMPDIR"
}

corpus_audit() {
  section "P11 corpus audit"
  "${UV_DEV[@]}" python scripts/run_corpus_audit.py \
    --corpus evals/judgment/corpus/p11-corpus.json \
    --output-json "$VERIFY_TMPDIR/opscat-corpus-audit.json" \
    --output-md "$VERIFY_TMPDIR/opscat-corpus-audit.md" >/tmp/opscat-corpus-audit-latest.json
  cp "$VERIFY_TMPDIR/opscat-corpus-audit.md" /tmp/opscat-corpus-audit-latest.md
  printf 'Wrote /tmp/opscat-corpus-audit-latest.md and %s/opscat-corpus-audit.json\n' "$VERIFY_TMPDIR"
}

real_dataset_eval() {
  section "P12 real dataset fixture evaluation"
  "${UV_DEV[@]}" python scripts/run_real_dataset_eval.py \
    --fixture-pack \
    --output-json "$VERIFY_TMPDIR/opscat-real-dataset-eval.json" \
    --output-md "$VERIFY_TMPDIR/opscat-real-dataset-eval.md" \
    --output-cases "$VERIFY_TMPDIR/opscat-real-dataset-cases.json" >/tmp/opscat-real-dataset-eval-latest.json
  cp "$VERIFY_TMPDIR/opscat-real-dataset-eval.md" /tmp/opscat-real-dataset-eval-latest.md
  printf 'Wrote /tmp/opscat-real-dataset-eval-latest.md and %s/opscat-real-dataset-eval.json\n' "$VERIFY_TMPDIR"
}

llm_context_smoke() {
  section "P13 LLM context builder smoke"
  "${UV_DEV[@]}" python scripts/build_llm_context.py \
    --cases evals/judgment/seed/cases.json \
    --case-id seed-loghub-injection-block \
    --output-json "$VERIFY_TMPDIR/opscat-llm-context.json" \
    --output-md "$VERIFY_TMPDIR/opscat-llm-context.md" >/tmp/opscat-llm-context-latest.json
  cp "$VERIFY_TMPDIR/opscat-llm-context.md" /tmp/opscat-llm-context-latest.md
  printf 'Wrote /tmp/opscat-llm-context-latest.md and %s/opscat-llm-context.json\n' "$VERIFY_TMPDIR"
}

llm_judgment_smoke() {
  section "P14 LLM judgment smoke"
  "${UV_DEV[@]}" python scripts/run_llm_judgment.py \
    --cases evals/judgment/seed/cases.json \
    --case-id seed-loghub-injection-block \
    --provider mock \
    --output-json "$VERIFY_TMPDIR/opscat-llm-judgment.json" \
    --output-md "$VERIFY_TMPDIR/opscat-llm-judgment.md" >/tmp/opscat-llm-judgment-latest.json
  cp "$VERIFY_TMPDIR/opscat-llm-judgment.md" /tmp/opscat-llm-judgment-latest.md
  printf 'Wrote /tmp/opscat-llm-judgment-latest.md and %s/opscat-llm-judgment.json\n' "$VERIFY_TMPDIR"
}

llm_provider_eval_smoke() {
  section "P16 LLM provider evaluation smoke"
  "${UV_DEV[@]}" python scripts/run_llm_provider_eval.py \
    --cases evals/judgment/seed/cases.json \
    --provider mock \
    --output-json "$VERIFY_TMPDIR/opscat-llm-provider-eval.json" \
    --output-md "$VERIFY_TMPDIR/opscat-llm-provider-eval.md" >/tmp/opscat-llm-provider-eval-latest.json
  cp "$VERIFY_TMPDIR/opscat-llm-provider-eval.md" /tmp/opscat-llm-provider-eval-latest.md
  printf 'Wrote /tmp/opscat-llm-provider-eval-latest.md and %s/opscat-llm-provider-eval.json\n' "$VERIFY_TMPDIR"
}


policy_calibration_smoke() {
  section "P17 policy calibration smoke"
  "${UV_DEV[@]}" python scripts/run_llm_provider_eval.py \
    --cases evals/judgment/seed/cases.json \
    --provider mock \
    --output-json "$VERIFY_TMPDIR/opscat-policy-calibration.json" \
    --output-md "$VERIFY_TMPDIR/opscat-policy-calibration.md" >/tmp/opscat-policy-calibration-latest.json
  cp "$VERIFY_TMPDIR/opscat-policy-calibration.md" /tmp/opscat-policy-calibration-latest.md
  printf 'Wrote /tmp/opscat-policy-calibration-latest.md and %s/opscat-policy-calibration.json\n' "$VERIFY_TMPDIR"
}


realtime_source_replay_smoke() {
  section "P18A realtime source replay smoke"
  cat >"$VERIFY_TMPDIR/p18a-smoke.log" <<'LOG'
ERROR api failed request one
ERROR api failed request two
ERROR api failed request three
LOG
  cat >"$VERIFY_TMPDIR/p18a-metric.csv" <<'CSV'
timestamp,value
2026-07-08T01:00:00Z,10
2026-07-08T01:01:00Z,50
CSV
  "${UV_DEV[@]}" python scripts/replay_realtime_sources.py \
    --log-file "$VERIFY_TMPDIR/p18a-smoke.log" \
    --metric-csv "$VERIFY_TMPDIR/p18a-metric.csv" \
    --output-json "$VERIFY_TMPDIR/opscat-realtime-replay.json" \
    --output-md "$VERIFY_TMPDIR/opscat-realtime-replay.md" >/tmp/opscat-realtime-replay-latest.json
  cp "$VERIFY_TMPDIR/opscat-realtime-replay.md" /tmp/opscat-realtime-replay-latest.md
  printf 'Wrote /tmp/opscat-realtime-replay-latest.md and %s/opscat-realtime-replay.json\n' "$VERIFY_TMPDIR"
}

model_quality_lab_smoke() {
  section "P18B model quality lab smoke"
  "${UV_DEV[@]}" python scripts/run_model_quality_eval.py \
    --cases evals/judgment/seed/cases.json \
    --provider mock \
    --max-cases 4 \
    --output-json "$VERIFY_TMPDIR/opscat-model-quality.json" \
    --output-md "$VERIFY_TMPDIR/opscat-model-quality.md" >/tmp/opscat-model-quality-latest.json
  cp "$VERIFY_TMPDIR/opscat-model-quality.md" /tmp/opscat-model-quality-latest.md
  printf 'Wrote /tmp/opscat-model-quality-latest.md and %s/opscat-model-quality.json\n' "$VERIFY_TMPDIR"
}

operator_improvement_loop_smoke() {
  section "P19 operator improvement loop smoke"
  cat >"$VERIFY_TMPDIR/p19-model-quality.json" <<'JSON'
{
  "provider": "mock",
  "model": "mock",
  "case_count": 1,
  "raw_provider_score": 0.5,
  "calibrated_score": 0.9,
  "calibration_delta": 0.4,
  "calibration_wins": 1,
  "failure_taxonomy_counts": {"unsafe_action_allowed": 1, "route_over_auto": 1},
  "results": [
    {
      "case_id": "p19-smoke-unsafe",
      "case_title": "Unsafe auto route smoke",
      "provider_route": "local_mock_auto_allowed",
      "final_route": "blocked",
      "raw_provider_score": 0.2,
      "calibrated_score": 1.0,
      "calibration_delta": 0.8,
      "failure_taxonomy": ["unsafe_action_allowed", "route_over_auto"],
      "quality_dimensions": {"safety": 0.0, "raw_route": 0.0},
      "raw_safe_actions": ["kubectl restart production"]
    }
  ]
}
JSON
  "${UV_DEV[@]}" python scripts/run_improvement_loop.py \
    --input-json "$VERIFY_TMPDIR/p19-model-quality.json" \
    --output-json "$VERIFY_TMPDIR/opscat-improvement-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-improvement-loop.md" \
    --regression-pack "$VERIFY_TMPDIR/opscat-p19-regression-pack.json" >/tmp/opscat-improvement-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-improvement-loop.md" /tmp/opscat-improvement-loop-latest.md
  printf 'Wrote /tmp/opscat-improvement-loop-latest.md and %s/opscat-improvement-loop.json\n' "$VERIFY_TMPDIR"
}

closed_loop_response_smoke() {
  section "P20 closed-loop response smoke"
  "${UV_DEV[@]}" python scripts/run_closed_loop_response.py \
    --cases evals/judgment/seed/cases.json \
    --case-id seed-nab-no-data \
    --provider mock \
    --output-json "$VERIFY_TMPDIR/opscat-closed-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-closed-loop.md" >/tmp/opscat-closed-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-closed-loop.md" /tmp/opscat-closed-loop-latest.md
  printf 'Wrote /tmp/opscat-closed-loop-latest.md and %s/opscat-closed-loop.json\n' "$VERIFY_TMPDIR"
}

runtime_loop_smoke() {
  section "P21 runtime loop smoke"
  "${UV_DEV[@]}" python scripts/run_runtime_loop.py \
    --cases evals/judgment/seed/cases.json \
    --max-cases 2 \
    --max-ticks 2 \
    --approval-mode auto_readonly \
    --output-json "$VERIFY_TMPDIR/opscat-runtime-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-runtime-loop.md" >/tmp/opscat-runtime-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-runtime-loop.md" /tmp/opscat-runtime-loop-latest.md
  printf 'Wrote /tmp/opscat-runtime-loop-latest.md and %s/opscat-runtime-loop.json\n' "$VERIFY_TMPDIR"
}

night_shift_drill_smoke() {
  section "P22 night-shift runtime drill smoke"
  "${UV_DEV[@]}" python scripts/run_night_shift_drill.py \
    --cases evals/judgment/seed/cases.json \
    --max-cases 4 \
    --max-ticks 4 \
    --approval-mode auto_readonly \
    --output-json "$VERIFY_TMPDIR/opscat-night-drill.json" \
    --output-md "$VERIFY_TMPDIR/opscat-night-drill.md" >/tmp/opscat-night-drill-latest.json
  cp "$VERIFY_TMPDIR/opscat-night-drill.md" /tmp/opscat-night-drill-latest.md
  printf 'Wrote /tmp/opscat-night-drill-latest.md and %s/opscat-night-drill.json\n' "$VERIFY_TMPDIR"
}

proactive_risk_sentinel_smoke() {
  section "P24 proactive risk sentinel smoke"
  "${UV_DEV[@]}" python scripts/run_proactive_risk_sentinel.py \
    --fixtures evals/proactive/seed/risk_windows.json \
    --max-windows 12 \
    --output-json "$VERIFY_TMPDIR/opscat-proactive-risk.json" \
    --output-md "$VERIFY_TMPDIR/opscat-proactive-risk.md" >/tmp/opscat-proactive-risk-latest.json
  cp "$VERIFY_TMPDIR/opscat-proactive-risk.md" /tmp/opscat-proactive-risk-latest.md
  printf 'Wrote /tmp/opscat-proactive-risk-latest.md and %s/opscat-proactive-risk.json\n' "$VERIFY_TMPDIR"
}

proactive_calibration_smoke() {
  section "P25 proactive calibration smoke"
  "${UV_DEV[@]}" python scripts/run_proactive_calibration.py \
    --fixtures evals/proactive/seed/risk_windows.json \
    --output-json "$VERIFY_TMPDIR/opscat-proactive-calibration.json" \
    --output-md "$VERIFY_TMPDIR/opscat-proactive-calibration.md" >/tmp/opscat-proactive-calibration-latest.json
  cp "$VERIFY_TMPDIR/opscat-proactive-calibration.md" /tmp/opscat-proactive-calibration-latest.md
  printf 'Wrote /tmp/opscat-proactive-calibration-latest.md and %s/opscat-proactive-calibration.json\n' "$VERIFY_TMPDIR"
}

telemetry_adapter_smoke() {
  section "P26 telemetry adapter smoke"
  "${UV_DEV[@]}" python scripts/run_telemetry_adapter.py \
    --source all \
    --fixture-dir evals/telemetry/fixtures \
    --output-json "$VERIFY_TMPDIR/opscat-telemetry-adapter.json" \
    --output-md "$VERIFY_TMPDIR/opscat-telemetry-adapter.md" >/tmp/opscat-telemetry-adapter-latest.json
  cp "$VERIFY_TMPDIR/opscat-telemetry-adapter.md" /tmp/opscat-telemetry-adapter-latest.md
  printf 'Wrote /tmp/opscat-telemetry-adapter-latest.md and %s/opscat-telemetry-adapter.json\n' "$VERIFY_TMPDIR"
}

connector_readiness_smoke() {
  section "P27 connector readiness smoke"
  "${UV_DEV[@]}" python scripts/run_connector_readiness.py \
    --manifests evals/connectors/readiness/read_only_sources.json \
    --output-json "$VERIFY_TMPDIR/opscat-connector-readiness.json" \
    --output-md "$VERIFY_TMPDIR/opscat-connector-readiness.md" >/tmp/opscat-connector-readiness-latest.json
  cp "$VERIFY_TMPDIR/opscat-connector-readiness.md" /tmp/opscat-connector-readiness-latest.md
  printf 'Wrote /tmp/opscat-connector-readiness-latest.md and %s/opscat-connector-readiness.json\n' "$VERIFY_TMPDIR"
}

read_only_polling_smoke() {
  section "P28 read-only polling smoke"
  "${UV_DEV[@]}" python scripts/run_read_only_polling.py \
    --jobs evals/polling/jobs/p28_polling_jobs.json \
    --readiness evals/connectors/readiness/read_only_sources.json \
    --ticks 1 \
    --output-json "$VERIFY_TMPDIR/opscat-read-only-polling.json" \
    --output-md "$VERIFY_TMPDIR/opscat-read-only-polling.md" >/tmp/opscat-read-only-polling-latest.json
  cp "$VERIFY_TMPDIR/opscat-read-only-polling.md" /tmp/opscat-read-only-polling-latest.md
  printf 'Wrote /tmp/opscat-read-only-polling-latest.md and %s/opscat-read-only-polling.json\n' "$VERIFY_TMPDIR"
}

telemetry_judgment_quality_smoke() {
  section "P29 telemetry judgment quality smoke"
  "${UV_DEV[@]}" python scripts/run_telemetry_judgment_eval.py \
    --cases evals/judgment/telemetry_grounded/p29_cases.json \
    --provider mock \
    --output-json "$VERIFY_TMPDIR/opscat-telemetry-judgment-quality.json" \
    --output-md "$VERIFY_TMPDIR/opscat-telemetry-judgment-quality.md" >/tmp/opscat-telemetry-judgment-quality-latest.json
  cp "$VERIFY_TMPDIR/opscat-telemetry-judgment-quality.md" /tmp/opscat-telemetry-judgment-quality-latest.md
  printf 'Wrote /tmp/opscat-telemetry-judgment-quality-latest.md and %s/opscat-telemetry-judgment-quality.json\n' "$VERIFY_TMPDIR"
}

controlled_remediation_smoke() {
  section "P30 controlled remediation smoke"
  "${UV_DEV[@]}" python scripts/run_controlled_remediation.py \
    --drills evals/remediation/p30_drills.json \
    --output-json "$VERIFY_TMPDIR/opscat-controlled-remediation.json" \
    --output-md "$VERIFY_TMPDIR/opscat-controlled-remediation.md" >/tmp/opscat-controlled-remediation-latest.json
  cp "$VERIFY_TMPDIR/opscat-controlled-remediation.md" /tmp/opscat-controlled-remediation-latest.md
  printf 'Wrote /tmp/opscat-controlled-remediation-latest.md and %s/opscat-controlled-remediation.json\n' "$VERIFY_TMPDIR"
}

operator_replacement_drill_smoke() {
  section "P31 operator replacement drill smoke"
  "${UV_DEV[@]}" python scripts/run_operator_replacement_drill.py \
    --scenarios evals/operator_replacement/p31_scenarios.json \
    --output-json "$VERIFY_TMPDIR/opscat-operator-replacement.json" \
    --output-md "$VERIFY_TMPDIR/opscat-operator-replacement.md" >/tmp/opscat-operator-replacement-latest.txt
  cp "$VERIFY_TMPDIR/opscat-operator-replacement.json" /tmp/opscat-operator-replacement-latest.json
  cp "$VERIFY_TMPDIR/opscat-operator-replacement.md" /tmp/opscat-operator-replacement-latest.md
  printf 'Wrote /tmp/opscat-operator-replacement-latest.md and %s/opscat-operator-replacement.json\n' "$VERIFY_TMPDIR"
}

real_telemetry_replay_smoke() {
  section "P32 real telemetry replay benchmark smoke"
  "${UV_DEV[@]}" python scripts/run_real_telemetry_replay_benchmark.py \
    --replay-pack evals/telemetry/replay/p32_replay_pack.json \
    --output-json "$VERIFY_TMPDIR/opscat-real-telemetry-replay.json" \
    --output-md "$VERIFY_TMPDIR/opscat-real-telemetry-replay.md" >/tmp/opscat-real-telemetry-replay-latest.txt
  cp "$VERIFY_TMPDIR/opscat-real-telemetry-replay.json" /tmp/opscat-real-telemetry-replay-latest.json
  cp "$VERIFY_TMPDIR/opscat-real-telemetry-replay.md" /tmp/opscat-real-telemetry-replay-latest.md
  printf 'Wrote /tmp/opscat-real-telemetry-replay-latest.md and %s/opscat-real-telemetry-replay.json\n' "$VERIFY_TMPDIR"
}

live_connector_dry_run_smoke() {
  section "P33 live connector dry-run smoke"
  "${UV_DEV[@]}" python scripts/run_live_connector_dry_run.py \
    --manifest evals/connectors/dry_run/p33_connectors.json \
    --output-json "$VERIFY_TMPDIR/opscat-live-connector-dry-run.json" \
    --output-md "$VERIFY_TMPDIR/opscat-live-connector-dry-run.md" >/tmp/opscat-live-connector-dry-run-latest.txt
  cp "$VERIFY_TMPDIR/opscat-live-connector-dry-run.json" /tmp/opscat-live-connector-dry-run-latest.json
  cp "$VERIFY_TMPDIR/opscat-live-connector-dry-run.md" /tmp/opscat-live-connector-dry-run-latest.md
  printf 'Wrote /tmp/opscat-live-connector-dry-run-latest.md and %s/opscat-live-connector-dry-run.json\n' "$VERIFY_TMPDIR"
}

read_only_polling_v2_smoke() {
  section "P34 read-only polling v2 smoke"
  "${UV_DEV[@]}" python scripts/run_read_only_polling_v2.py \
    --jobs evals/polling/v2/p34_polling_jobs.json \
    --dry-run-manifest evals/connectors/dry_run/p33_connectors.json \
    --output-json "$VERIFY_TMPDIR/opscat-read-only-polling-v2.json" \
    --output-md "$VERIFY_TMPDIR/opscat-read-only-polling-v2.md" >/tmp/opscat-read-only-polling-v2-latest.txt
  cp "$VERIFY_TMPDIR/opscat-read-only-polling-v2.json" /tmp/opscat-read-only-polling-v2-latest.json
  cp "$VERIFY_TMPDIR/opscat-read-only-polling-v2.md" /tmp/opscat-read-only-polling-v2-latest.md
  printf 'Wrote /tmp/opscat-read-only-polling-v2-latest.md and %s/opscat-read-only-polling-v2.json\n' "$VERIFY_TMPDIR"
}

incident_shadow_mode_smoke() {
  section "P35 incident shadow mode smoke"
  "${UV_DEV[@]}" python scripts/run_incident_shadow_mode.py \
    --cases evals/shadow/p35_shadow_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-incident-shadow-mode.json" \
    --output-md "$VERIFY_TMPDIR/opscat-incident-shadow-mode.md" >/tmp/opscat-incident-shadow-mode-latest.txt
  cp "$VERIFY_TMPDIR/opscat-incident-shadow-mode.json" /tmp/opscat-incident-shadow-mode-latest.json
  cp "$VERIFY_TMPDIR/opscat-incident-shadow-mode.md" /tmp/opscat-incident-shadow-mode-latest.md
  printf 'Wrote /tmp/opscat-incident-shadow-mode-latest.md and %s/opscat-incident-shadow-mode.json\n' "$VERIFY_TMPDIR"
}

approval_control_plane_smoke() {
  section "P36 approval control plane smoke"
  "${UV_DEV[@]}" python scripts/run_approval_control_plane.py \
    --fixture evals/approval/p36_profiles.json \
    --output-json "$VERIFY_TMPDIR/opscat-approval-control-plane.json" \
    --output-md "$VERIFY_TMPDIR/opscat-approval-control-plane.md" >/tmp/opscat-approval-control-plane-latest.txt
  cp "$VERIFY_TMPDIR/opscat-approval-control-plane.json" /tmp/opscat-approval-control-plane-latest.json
  cp "$VERIFY_TMPDIR/opscat-approval-control-plane.md" /tmp/opscat-approval-control-plane-latest.md
  printf 'Wrote /tmp/opscat-approval-control-plane-latest.md and %s/opscat-approval-control-plane.json\n' "$VERIFY_TMPDIR"
}

open_source_config_hardening_smoke() {
  section "P37 open-source config hardening smoke"
  "${UV_DEV[@]}" python scripts/run_open_source_config_hardening.py \
    --manifest evals/config/p37_config_manifest.json \
    --output-json "$VERIFY_TMPDIR/opscat-open-source-config-hardening.json" \
    --output-md "$VERIFY_TMPDIR/opscat-open-source-config-hardening.md" >/tmp/opscat-open-source-config-hardening-latest.txt
  cp "$VERIFY_TMPDIR/opscat-open-source-config-hardening.json" /tmp/opscat-open-source-config-hardening-latest.json
  cp "$VERIFY_TMPDIR/opscat-open-source-config-hardening.md" /tmp/opscat-open-source-config-hardening-latest.md
  printf 'Wrote /tmp/opscat-open-source-config-hardening-latest.md and %s/opscat-open-source-config-hardening.json\n' "$VERIFY_TMPDIR"
}

agent_evaluation_dashboard_smoke() {
  section "P38 agent evaluation dashboard smoke"
  "${UV_DEV[@]}" python scripts/run_agent_evaluation_dashboard.py \
    --sources evals/dashboard/p38_sources.json \
    --output-json "$VERIFY_TMPDIR/opscat-agent-evaluation-dashboard.json" \
    --output-md "$VERIFY_TMPDIR/opscat-agent-evaluation-dashboard.md" >/tmp/opscat-agent-evaluation-dashboard-latest.txt
  cp "$VERIFY_TMPDIR/opscat-agent-evaluation-dashboard.json" /tmp/opscat-agent-evaluation-dashboard-latest.json
  cp "$VERIFY_TMPDIR/opscat-agent-evaluation-dashboard.md" /tmp/opscat-agent-evaluation-dashboard-latest.md
  printf 'Wrote /tmp/opscat-agent-evaluation-dashboard-latest.md and %s/opscat-agent-evaluation-dashboard.json\n' "$VERIFY_TMPDIR"
}

runbook_learning_loop_smoke() {
  section "P39 runbook learning loop smoke"
  "${UV_DEV[@]}" python scripts/run_runbook_learning_loop.py \
    --sources evals/learning/p39_sources.json \
    --output-json "$VERIFY_TMPDIR/opscat-runbook-learning-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-runbook-learning-loop.md" >/tmp/opscat-runbook-learning-loop-latest.txt
  cp "$VERIFY_TMPDIR/opscat-runbook-learning-loop.json" /tmp/opscat-runbook-learning-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-runbook-learning-loop.md" /tmp/opscat-runbook-learning-loop-latest.md
  printf 'Wrote /tmp/opscat-runbook-learning-loop-latest.md and %s/opscat-runbook-learning-loop.json\n' "$VERIFY_TMPDIR"
}

production_readiness_milestone_smoke() {
  section "P40 production-readiness milestone smoke"
  "${UV_DEV[@]}" python scripts/run_production_readiness_milestone.py \
    --sources evals/readiness/p40_sources.json \
    --output-json "$VERIFY_TMPDIR/opscat-production-readiness-milestone.json" \
    --output-md "$VERIFY_TMPDIR/opscat-production-readiness-milestone.md" >/tmp/opscat-production-readiness-milestone-latest.txt
  cp "$VERIFY_TMPDIR/opscat-production-readiness-milestone.json" /tmp/opscat-production-readiness-milestone-latest.json
  cp "$VERIFY_TMPDIR/opscat-production-readiness-milestone.md" /tmp/opscat-production-readiness-milestone-latest.md
  printf 'Wrote /tmp/opscat-production-readiness-milestone-latest.md and %s/opscat-production-readiness-milestone.json\n' "$VERIFY_TMPDIR"
}

raw_real_dataset_replay_smoke() {
  section "P41 raw real dataset replay smoke"
  "${UV_DEV[@]}" python scripts/run_raw_real_dataset_replay.py \
    --sources evals/real_datasets/raw/p41_sources.json \
    --output-json "$VERIFY_TMPDIR/opscat-raw-real-dataset-replay.json" \
    --output-md "$VERIFY_TMPDIR/opscat-raw-real-dataset-replay.md" >/tmp/opscat-raw-real-dataset-replay-latest.txt
  cp "$VERIFY_TMPDIR/opscat-raw-real-dataset-replay.json" /tmp/opscat-raw-real-dataset-replay-latest.json
  cp "$VERIFY_TMPDIR/opscat-raw-real-dataset-replay.md" /tmp/opscat-raw-real-dataset-replay-latest.md
  printf 'Wrote /tmp/opscat-raw-real-dataset-replay-latest.md and %s/opscat-raw-real-dataset-replay.json\n' "$VERIFY_TMPDIR"
}

external_dataset_acquisition_smoke() {
  section "P42 external dataset acquisition smoke"
  "${UV_DEV[@]}" python scripts/prepare_external_datasets.py \
    --manifest evals/real_datasets/external/p42_manifest.json \
    --output-json "$VERIFY_TMPDIR/opscat-external-dataset-acquisition.json" \
    --output-md "$VERIFY_TMPDIR/opscat-external-dataset-acquisition.md" >/tmp/opscat-external-dataset-acquisition-latest.txt
  cp "$VERIFY_TMPDIR/opscat-external-dataset-acquisition.json" /tmp/opscat-external-dataset-acquisition-latest.json
  cp "$VERIFY_TMPDIR/opscat-external-dataset-acquisition.md" /tmp/opscat-external-dataset-acquisition-latest.md
  printf 'Wrote /tmp/opscat-external-dataset-acquisition-latest.md and %s/opscat-external-dataset-acquisition.json\n' "$VERIFY_TMPDIR"
}

public_dataset_benchmark_smoke() {
  section "P43 public dataset benchmark smoke"
  "${UV_DEV[@]}" python scripts/run_public_dataset_benchmark.py \
    --manifest evals/real_datasets/external/p43_public_benchmark_manifest.json \
    --artifact-root "$VERIFY_TMPDIR/p43-public-artifacts" \
    --materialized-root "$VERIFY_TMPDIR/p43-public-materialized" \
    --output-json "$VERIFY_TMPDIR/opscat-public-dataset-benchmark.json" \
    --output-md "$VERIFY_TMPDIR/opscat-public-dataset-benchmark.md" >/tmp/opscat-public-dataset-benchmark-latest.txt
  cp "$VERIFY_TMPDIR/opscat-public-dataset-benchmark.json" /tmp/opscat-public-dataset-benchmark-latest.json
  cp "$VERIFY_TMPDIR/opscat-public-dataset-benchmark.md" /tmp/opscat-public-dataset-benchmark-latest.md
  printf 'Wrote /tmp/opscat-public-dataset-benchmark-latest.md and %s/opscat-public-dataset-benchmark.json\n' "$VERIFY_TMPDIR"
}

public_dataset_matrix_smoke() {
  section "P44 public dataset matrix smoke"
  "${UV_DEV[@]}" python scripts/run_public_dataset_matrix.py \
    --manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
    --artifact-root "$VERIFY_TMPDIR/p44-public-artifacts" \
    --materialized-root "$VERIFY_TMPDIR/p44-public-materialized" \
    --output-json "$VERIFY_TMPDIR/opscat-public-dataset-matrix.json" \
    --output-md "$VERIFY_TMPDIR/opscat-public-dataset-matrix.md" >/tmp/opscat-public-dataset-matrix-latest.txt
  cp "$VERIFY_TMPDIR/opscat-public-dataset-matrix.json" /tmp/opscat-public-dataset-matrix-latest.json
  cp "$VERIFY_TMPDIR/opscat-public-dataset-matrix.md" /tmp/opscat-public-dataset-matrix-latest.md
  printf 'Wrote /tmp/opscat-public-dataset-matrix-latest.md and %s/opscat-public-dataset-matrix.json\n' "$VERIFY_TMPDIR"
}

evidence_grounded_judgment_smoke() {
  section "P45 evidence-grounded judgment smoke"
  "${UV_DEV[@]}" python scripts/run_evidence_grounded_judgment.py \
    --cases evals/investigator/p45_judgment_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-evidence-grounded-judgment.json" \
    --output-md "$VERIFY_TMPDIR/opscat-evidence-grounded-judgment.md" >/tmp/opscat-evidence-grounded-judgment-latest.txt
  cp "$VERIFY_TMPDIR/opscat-evidence-grounded-judgment.json" /tmp/opscat-evidence-grounded-judgment-latest.json
  cp "$VERIFY_TMPDIR/opscat-evidence-grounded-judgment.md" /tmp/opscat-evidence-grounded-judgment-latest.md
  printf 'Wrote /tmp/opscat-evidence-grounded-judgment-latest.md and %s/opscat-evidence-grounded-judgment.json\n' "$VERIFY_TMPDIR"
}

evidence_sufficiency_gate_v2_smoke() {
  section "P76 evidence sufficiency gate v2 smoke"
  "${UV_DEV[@]}" python scripts/run_evidence_sufficiency_gate_v2.py \
    --cases evals/investigator/p45_judgment_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-evidence-sufficiency-gate-v2.json" \
    --output-md "$VERIFY_TMPDIR/opscat-evidence-sufficiency-gate-v2.md" >/tmp/opscat-evidence-sufficiency-gate-v2-latest.txt
  cp "$VERIFY_TMPDIR/opscat-evidence-sufficiency-gate-v2.md" /tmp/opscat-evidence-sufficiency-gate-v2-latest.md
  printf 'Wrote /tmp/opscat-evidence-sufficiency-gate-v2-latest.md and %s/opscat-evidence-sufficiency-gate-v2.json\n' "$VERIFY_TMPDIR"
}

investigator_loop_smoke() {
  section "P46 investigator loop smoke"
  "${UV_DEV[@]}" python scripts/run_investigator_loop.py \
    --cases evals/investigator/p46_investigation_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-investigator-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-investigator-loop.md" >/tmp/opscat-investigator-loop-latest.txt
  cp "$VERIFY_TMPDIR/opscat-investigator-loop.json" /tmp/opscat-investigator-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-investigator-loop.md" /tmp/opscat-investigator-loop-latest.md
  printf 'Wrote /tmp/opscat-investigator-loop-latest.md and %s/opscat-investigator-loop.json\n' "$VERIFY_TMPDIR"
}

tool_selection_planner_smoke() {
  section "P47 tool selection planner smoke"
  "${UV_DEV[@]}" python scripts/run_tool_selection_planner.py \
    --cases evals/investigator/p47_tool_selection_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-tool-selection-planner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-tool-selection-planner.md" >/tmp/opscat-tool-selection-planner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-tool-selection-planner.json" /tmp/opscat-tool-selection-planner-latest.json
  cp "$VERIFY_TMPDIR/opscat-tool-selection-planner.md" /tmp/opscat-tool-selection-planner-latest.md
  printf 'Wrote /tmp/opscat-tool-selection-planner-latest.md and %s/opscat-tool-selection-planner.json\n' "$VERIFY_TMPDIR"
}

hypothesis_reranker_smoke() {
  section "P48 hypothesis re-ranker smoke"
  "${UV_DEV[@]}" python scripts/run_hypothesis_reranker.py \
    --cases evals/investigator/p48_rerank_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-hypothesis-reranker.json" \
    --output-md "$VERIFY_TMPDIR/opscat-hypothesis-reranker.md" >/tmp/opscat-hypothesis-reranker-latest.txt
  cp "$VERIFY_TMPDIR/opscat-hypothesis-reranker.json" /tmp/opscat-hypothesis-reranker-latest.json
  cp "$VERIFY_TMPDIR/opscat-hypothesis-reranker.md" /tmp/opscat-hypothesis-reranker-latest.md
  printf 'Wrote /tmp/opscat-hypothesis-reranker-latest.md and %s/opscat-hypothesis-reranker.json\n' "$VERIFY_TMPDIR"
}

remediation_verification_loop_smoke() {
  section "P49 remediation verification loop smoke"
  "${UV_DEV[@]}" python scripts/run_remediation_verification_loop.py \
    --cases evals/investigator/p49_remediation_verification_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-remediation-verification-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-remediation-verification-loop.md" >/tmp/opscat-remediation-verification-loop-latest.txt
  cp "$VERIFY_TMPDIR/opscat-remediation-verification-loop.json" /tmp/opscat-remediation-verification-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-remediation-verification-loop.md" /tmp/opscat-remediation-verification-loop-latest.md
  printf 'Wrote /tmp/opscat-remediation-verification-loop-latest.md and %s/opscat-remediation-verification-loop.json\n' "$VERIFY_TMPDIR"
}

recovery_proof_engine_smoke() {
  section "P77 recovery proof engine smoke"
  "${UV_DEV[@]}" python scripts/run_recovery_proof_engine.py \
    --cases evals/investigator/p49_remediation_verification_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-recovery-proof-engine.json" \
    --output-md "$VERIFY_TMPDIR/opscat-recovery-proof-engine.md" >/tmp/opscat-recovery-proof-engine-latest.txt
  cp "$VERIFY_TMPDIR/opscat-recovery-proof-engine.md" /tmp/opscat-recovery-proof-engine-latest.md
  printf 'Wrote /tmp/opscat-recovery-proof-engine-latest.md and %s/opscat-recovery-proof-engine.json\n' "$VERIFY_TMPDIR"
}

runbook_simulation_tournament_smoke() {
  section "P78 runbook simulation tournament smoke"
  "${UV_DEV[@]}" python scripts/run_runbook_simulation_tournament.py \
    --candidates evals/runbooks/p78_runbook_candidates.json \
    --output-json "$VERIFY_TMPDIR/opscat-runbook-simulation-tournament.json" \
    --output-md "$VERIFY_TMPDIR/opscat-runbook-simulation-tournament.md" >/tmp/opscat-runbook-simulation-tournament-latest.txt
  cp "$VERIFY_TMPDIR/opscat-runbook-simulation-tournament.md" /tmp/opscat-runbook-simulation-tournament-latest.md
  printf 'Wrote /tmp/opscat-runbook-simulation-tournament-latest.md and %s/opscat-runbook-simulation-tournament.json\n' "$VERIFY_TMPDIR"
}

action_sandbox_hardening_smoke() {
  section "P79 action sandbox hardening smoke"
  "${UV_DEV[@]}" python scripts/run_action_sandbox_hardening.py \
    --cases evals/actions/p79_action_sandbox_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-action-sandbox-hardening.json" \
    --output-md "$VERIFY_TMPDIR/opscat-action-sandbox-hardening.md" >/tmp/opscat-action-sandbox-hardening-latest.txt
  cp "$VERIFY_TMPDIR/opscat-action-sandbox-hardening.md" /tmp/opscat-action-sandbox-hardening-latest.md
  printf 'Wrote /tmp/opscat-action-sandbox-hardening-latest.md and %s/opscat-action-sandbox-hardening.json\n' "$VERIFY_TMPDIR"
}

approval_automation_policy_lab_smoke() {
  section "P80 approval automation policy lab smoke"
  "${UV_DEV[@]}" python scripts/run_approval_automation_policy_lab.py \
    --cases evals/policy/p80_approval_automation_policy_lab.json \
    --output-json "$VERIFY_TMPDIR/opscat-approval-automation-policy-lab.json" \
    --output-md "$VERIFY_TMPDIR/opscat-approval-automation-policy-lab.md" >/tmp/opscat-approval-automation-policy-lab-latest.txt
  cp "$VERIFY_TMPDIR/opscat-approval-automation-policy-lab.md" /tmp/opscat-approval-automation-policy-lab-latest.md
  printf 'Wrote /tmp/opscat-approval-automation-policy-lab-latest.md and %s/opscat-approval-automation-policy-lab.json\n' "$VERIFY_TMPDIR"
}

rollback_pr_draft_automation_smoke() {
  section "P81 rollback PR draft automation smoke"
  "${UV_DEV[@]}" python scripts/run_rollback_pr_draft_automation.py \
    --cases evals/policy/p81_rollback_pr_draft_automation.json \
    --output-json "$VERIFY_TMPDIR/opscat-rollback-pr-draft-automation.json" \
    --output-md "$VERIFY_TMPDIR/opscat-rollback-pr-draft-automation.md" >/tmp/opscat-rollback-pr-draft-automation-latest.txt
  cp "$VERIFY_TMPDIR/opscat-rollback-pr-draft-automation.md" /tmp/opscat-rollback-pr-draft-automation-latest.md
  printf 'Wrote /tmp/opscat-rollback-pr-draft-automation-latest.md and %s/opscat-rollback-pr-draft-automation.json\n' "$VERIFY_TMPDIR"
}

slack_ticket_draft_automation_smoke() {
  section "P82 slack and ticket draft automation smoke"
  "${UV_DEV[@]}" python scripts/run_slack_ticket_draft_automation.py \
    --cases evals/policy/p82_slack_ticket_draft_automation.json \
    --output-json "$VERIFY_TMPDIR/opscat-slack-ticket-draft-automation.json" \
    --output-md "$VERIFY_TMPDIR/opscat-slack-ticket-draft-automation.md" >/tmp/opscat-slack-ticket-draft-automation-latest.txt
  cp "$VERIFY_TMPDIR/opscat-slack-ticket-draft-automation.md" /tmp/opscat-slack-ticket-draft-automation-latest.md
  printf 'Wrote /tmp/opscat-slack-ticket-draft-automation-latest.md and %s/opscat-slack-ticket-draft-automation.json\n' "$VERIFY_TMPDIR"
}

post_action_outcome_monitor_smoke() {
  section "P83 post-action outcome monitor smoke"
  "${UV_DEV[@]}" python scripts/run_post_action_outcome_monitor.py \
    --cases evals/actions/p83_post_action_outcome_monitor.json \
    --output-json "$VERIFY_TMPDIR/opscat-post-action-outcome-monitor.json" \
    --output-md "$VERIFY_TMPDIR/opscat-post-action-outcome-monitor.md" >/tmp/opscat-post-action-outcome-monitor-latest.txt
  cp "$VERIFY_TMPDIR/opscat-post-action-outcome-monitor.md" /tmp/opscat-post-action-outcome-monitor-latest.md
  printf 'Wrote /tmp/opscat-post-action-outcome-monitor-latest.md and %s/opscat-post-action-outcome-monitor.json\n' "$VERIFY_TMPDIR"
}

outcome_driven_next_action_planner_smoke() {
  section "P84 outcome-driven next action planner smoke"
  "${UV_DEV[@]}" python scripts/run_outcome_driven_next_action_planner.py \
    --cases evals/actions/p84_outcome_driven_next_action_planner.json \
    --output-json "$VERIFY_TMPDIR/opscat-outcome-driven-next-action-planner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-outcome-driven-next-action-planner.md" >/tmp/opscat-outcome-driven-next-action-planner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-outcome-driven-next-action-planner.md" /tmp/opscat-outcome-driven-next-action-planner-latest.md
  printf 'Wrote /tmp/opscat-outcome-driven-next-action-planner-latest.md and %s/opscat-outcome-driven-next-action-planner.json\n' "$VERIFY_TMPDIR"
}

local_autonomous_supervisor_loop_smoke() {
  section "P85 local autonomous supervisor loop smoke"
  "${UV_DEV[@]}" python scripts/run_local_autonomous_supervisor_loop.py \
    --cases evals/actions/p85_local_autonomous_supervisor_loop.json \
    --output-json "$VERIFY_TMPDIR/opscat-local-autonomous-supervisor-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-local-autonomous-supervisor-loop.md" >/tmp/opscat-local-autonomous-supervisor-loop-latest.txt
  cp "$VERIFY_TMPDIR/opscat-local-autonomous-supervisor-loop.md" /tmp/opscat-local-autonomous-supervisor-loop-latest.md
  printf 'Wrote /tmp/opscat-local-autonomous-supervisor-loop-latest.md and %s/opscat-local-autonomous-supervisor-loop.json\n' "$VERIFY_TMPDIR"
}

resumable_local_supervisor_runner_smoke() {
  section "P86 resumable local supervisor runner smoke"
  "${UV_DEV[@]}" python scripts/run_resumable_local_supervisor_runner.py \
    --cases evals/actions/p86_resumable_local_supervisor_runner.json \
    --output-json "$VERIFY_TMPDIR/opscat-resumable-local-supervisor-runner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-resumable-local-supervisor-runner.md" >/tmp/opscat-resumable-local-supervisor-runner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-resumable-local-supervisor-runner.md" /tmp/opscat-resumable-local-supervisor-runner-latest.md
  printf 'Wrote /tmp/opscat-resumable-local-supervisor-runner-latest.md and %s/opscat-resumable-local-supervisor-runner.json\n' "$VERIFY_TMPDIR"
}

supervisor_run_report_artifact_smoke() {
  section "P87 supervisor run report artifact smoke"
  "${UV_DEV[@]}" python scripts/run_supervisor_run_report_artifact.py \
    --cases evals/actions/p87_supervisor_run_report_artifact.json \
    --output-json "$VERIFY_TMPDIR/opscat-supervisor-run-report-artifact.json" \
    --output-md "$VERIFY_TMPDIR/opscat-supervisor-run-report-artifact.md" >/tmp/opscat-supervisor-run-report-artifact-latest.txt
  cp "$VERIFY_TMPDIR/opscat-supervisor-run-report-artifact.md" /tmp/opscat-supervisor-run-report-artifact-latest.md
  printf 'Wrote /tmp/opscat-supervisor-run-report-artifact-latest.md and %s/opscat-supervisor-run-report-artifact.json\n' "$VERIFY_TMPDIR"
}

bounded_local_supervisor_scheduler_smoke() {
  section "P88 bounded local supervisor scheduler smoke"
  "${UV_DEV[@]}" python scripts/run_bounded_local_supervisor_scheduler.py \
    --cases evals/actions/p88_bounded_local_supervisor_scheduler.json \
    --output-json "$VERIFY_TMPDIR/opscat-bounded-local-supervisor-scheduler.json" \
    --output-md "$VERIFY_TMPDIR/opscat-bounded-local-supervisor-scheduler.md" >/tmp/opscat-bounded-local-supervisor-scheduler-latest.txt
  cp "$VERIFY_TMPDIR/opscat-bounded-local-supervisor-scheduler.md" /tmp/opscat-bounded-local-supervisor-scheduler-latest.md
  printf 'Wrote /tmp/opscat-bounded-local-supervisor-scheduler-latest.md and %s/opscat-bounded-local-supervisor-scheduler.json\n' "$VERIFY_TMPDIR"
}

safe_local_auto_run_entrypoint_smoke() {
  section "P89 safe local auto-run entrypoint smoke"
  "${UV_DEV[@]}" python scripts/run_safe_local_auto_run_entrypoint.py \
    --cases evals/actions/p89_safe_local_auto_run_entrypoint.json \
    --output-json "$VERIFY_TMPDIR/opscat-safe-local-auto-run-entrypoint.json" \
    --output-md "$VERIFY_TMPDIR/opscat-safe-local-auto-run-entrypoint.md" >/tmp/opscat-safe-local-auto-run-entrypoint-latest.txt
  cp "$VERIFY_TMPDIR/opscat-safe-local-auto-run-entrypoint.md" /tmp/opscat-safe-local-auto-run-entrypoint-latest.md
  printf 'Wrote /tmp/opscat-safe-local-auto-run-entrypoint-latest.md and %s/opscat-safe-local-auto-run-entrypoint.json\n' "$VERIFY_TMPDIR"
}

safe_auto_run_readiness_gate_smoke() {
  section "P90 safe auto-run readiness gate smoke"
  "${UV_DEV[@]}" python scripts/run_safe_auto_run_readiness_gate.py \
    --cases evals/actions/p90_safe_auto_run_readiness_gate.json \
    --output-json "$VERIFY_TMPDIR/opscat-safe-auto-run-readiness-gate.json" \
    --output-md "$VERIFY_TMPDIR/opscat-safe-auto-run-readiness-gate.md" >/tmp/opscat-safe-auto-run-readiness-gate-latest.txt
  cp "$VERIFY_TMPDIR/opscat-safe-auto-run-readiness-gate.md" /tmp/opscat-safe-auto-run-readiness-gate-latest.md
  printf 'Wrote /tmp/opscat-safe-auto-run-readiness-gate-latest.md and %s/opscat-safe-auto-run-readiness-gate.json\n' "$VERIFY_TMPDIR"
}

readiness_gap_remediation_planner_smoke() {
  section "P91 readiness gap remediation planner smoke"
  "${UV_DEV[@]}" python scripts/run_readiness_gap_remediation_planner.py \
    --cases evals/actions/p91_readiness_gap_remediation_planner.json \
    --output-json "$VERIFY_TMPDIR/opscat-readiness-gap-remediation-planner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-readiness-gap-remediation-planner.md" >/tmp/opscat-readiness-gap-remediation-planner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-readiness-gap-remediation-planner.md" /tmp/opscat-readiness-gap-remediation-planner-latest.md
  printf 'Wrote /tmp/opscat-readiness-gap-remediation-planner-latest.md and %s/opscat-readiness-gap-remediation-planner.json\n' "$VERIFY_TMPDIR"
}

operator_replacement_acceptance_drill_v3_smoke() {
  section "P92 operator replacement acceptance drill v3 smoke"
  "${UV_DEV[@]}" python scripts/run_operator_replacement_acceptance_drill_v3.py \
    --cases evals/actions/p92_operator_replacement_acceptance_drill_v3.json \
    --output-json "$VERIFY_TMPDIR/opscat-operator-replacement-acceptance-drill-v3.json" \
    --output-md "$VERIFY_TMPDIR/opscat-operator-replacement-acceptance-drill-v3.md" >/tmp/opscat-operator-replacement-acceptance-drill-v3-latest.txt
  cp "$VERIFY_TMPDIR/opscat-operator-replacement-acceptance-drill-v3.md" /tmp/opscat-operator-replacement-acceptance-drill-v3-latest.md
  printf 'Wrote /tmp/opscat-operator-replacement-acceptance-drill-v3-latest.md and %s/opscat-operator-replacement-acceptance-drill-v3.json\n' "$VERIFY_TMPDIR"
}

portfolio_demo_pack_smoke() {
  section "P93 portfolio demo pack smoke"
  "${UV_DEV[@]}" python scripts/run_portfolio_demo_pack.py \
    --input evals/actions/p93_portfolio_demo_pack.json \
    --output-json "$VERIFY_TMPDIR/opscat-portfolio-demo-pack.json" \
    --output-md "$VERIFY_TMPDIR/opscat-portfolio-demo-pack.md" >/tmp/opscat-portfolio-demo-pack-latest.txt
  cp "$VERIFY_TMPDIR/opscat-portfolio-demo-pack.md" /tmp/opscat-portfolio-demo-pack-latest.md
  printf 'Wrote /tmp/opscat-portfolio-demo-pack-latest.md and %s/opscat-portfolio-demo-pack.json\n' "$VERIFY_TMPDIR"
}

operator_transcript_demo_smoke() {
  section "P94 operator transcript demo smoke"
  "${UV_DEV[@]}" python scripts/run_operator_transcript_demo.py \
    --input evals/actions/p94_operator_transcript_demo.json \
    --output-json "$VERIFY_TMPDIR/opscat-operator-transcript-demo.json" \
    --output-md "$VERIFY_TMPDIR/opscat-operator-transcript-demo.md" >/tmp/opscat-operator-transcript-demo-latest.txt
  cp "$VERIFY_TMPDIR/opscat-operator-transcript-demo.md" /tmp/opscat-operator-transcript-demo-latest.md
  printf 'Wrote /tmp/opscat-operator-transcript-demo-latest.md and %s/opscat-operator-transcript-demo.json\n' "$VERIFY_TMPDIR"
}

night_operator_drill_v2_smoke() {
  section "P50 night operator drill v2 smoke"
  "${UV_DEV[@]}" python scripts/run_night_operator_drill_v2.py \
    --drills evals/investigator/p50_night_operator_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-night-operator-drill-v2.json" \
    --output-md "$VERIFY_TMPDIR/opscat-night-operator-drill-v2.md" >/tmp/opscat-night-operator-drill-v2-latest.txt
  cp "$VERIFY_TMPDIR/opscat-night-operator-drill-v2.json" /tmp/opscat-night-operator-drill-v2-latest.json
  cp "$VERIFY_TMPDIR/opscat-night-operator-drill-v2.md" /tmp/opscat-night-operator-drill-v2-latest.md
  printf 'Wrote /tmp/opscat-night-operator-drill-v2-latest.md and %s/opscat-night-operator-drill-v2.json\n' "$VERIFY_TMPDIR"
}

operator_judgment_benchmark_v2_smoke() {
  section "P51 operator judgment benchmark v2 smoke"
  "${UV_DEV[@]}" python scripts/run_operator_judgment_benchmark_v2.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-operator-judgment-benchmark-v2.json" \
    --output-md "$VERIFY_TMPDIR/opscat-operator-judgment-benchmark-v2.md" >/tmp/opscat-operator-judgment-benchmark-v2-latest.txt
  cp "$VERIFY_TMPDIR/opscat-operator-judgment-benchmark-v2.json" /tmp/opscat-operator-judgment-benchmark-v2-latest.json
  cp "$VERIFY_TMPDIR/opscat-operator-judgment-benchmark-v2.md" /tmp/opscat-operator-judgment-benchmark-v2-latest.md
  printf 'Wrote /tmp/opscat-operator-judgment-benchmark-v2-latest.md and %s/opscat-operator-judgment-benchmark-v2.json\n' "$VERIFY_TMPDIR"
}

failure_mining_loop_smoke() {
  section "P52 failure mining loop smoke"
  "${UV_DEV[@]}" python scripts/run_failure_mining_loop.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-failure-mining-loop.json" \
    --output-md "$VERIFY_TMPDIR/opscat-failure-mining-loop.md" >/tmp/opscat-failure-mining-loop-latest.txt
  cp "$VERIFY_TMPDIR/opscat-failure-mining-loop.json" /tmp/opscat-failure-mining-loop-latest.json
  cp "$VERIFY_TMPDIR/opscat-failure-mining-loop.md" /tmp/opscat-failure-mining-loop-latest.md
  printf 'Wrote /tmp/opscat-failure-mining-loop-latest.md and %s/opscat-failure-mining-loop.json\n' "$VERIFY_TMPDIR"
}

failure_driven_improvement_pack_smoke() {
  section "P53 failure-driven improvement pack smoke"
  "${UV_DEV[@]}" python scripts/run_failure_driven_improvement_pack.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-failure-driven-improvement-pack.json" \
    --output-md "$VERIFY_TMPDIR/opscat-failure-driven-improvement-pack.md" >/tmp/opscat-failure-driven-improvement-pack-latest.txt
  cp "$VERIFY_TMPDIR/opscat-failure-driven-improvement-pack.json" /tmp/opscat-failure-driven-improvement-pack-latest.json
  cp "$VERIFY_TMPDIR/opscat-failure-driven-improvement-pack.md" /tmp/opscat-failure-driven-improvement-pack-latest.md
  printf 'Wrote /tmp/opscat-failure-driven-improvement-pack-latest.md and %s/opscat-failure-driven-improvement-pack.json\n' "$VERIFY_TMPDIR"
}

failure_driven_benchmark_improvement_smoke() {
  section "P54 failure-driven benchmark improvement smoke"
  "${UV_DEV[@]}" python scripts/run_failure_driven_benchmark_improvement.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-failure-driven-benchmark-improvement.json" \
    --output-md "$VERIFY_TMPDIR/opscat-failure-driven-benchmark-improvement.md" >/tmp/opscat-failure-driven-benchmark-improvement-latest.txt
  cp "$VERIFY_TMPDIR/opscat-failure-driven-benchmark-improvement.json" /tmp/opscat-failure-driven-benchmark-improvement-latest.json
  cp "$VERIFY_TMPDIR/opscat-failure-driven-benchmark-improvement.md" /tmp/opscat-failure-driven-benchmark-improvement-latest.md
  printf 'Wrote /tmp/opscat-failure-driven-benchmark-improvement-latest.md and %s/opscat-failure-driven-benchmark-improvement.json\n' "$VERIFY_TMPDIR"
}

candidate_benchmark_promotion_gate_smoke() {
  section "P55 candidate benchmark promotion gate smoke"
  "${UV_DEV[@]}" python scripts/run_candidate_benchmark_promotion_gate.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-candidate-benchmark-promotion-gate.json" \
    --output-md "$VERIFY_TMPDIR/opscat-candidate-benchmark-promotion-gate.md" >/tmp/opscat-candidate-benchmark-promotion-gate-latest.txt
  cp "$VERIFY_TMPDIR/opscat-candidate-benchmark-promotion-gate.md" /tmp/opscat-candidate-benchmark-promotion-gate-latest.md
  printf 'Wrote /tmp/opscat-candidate-benchmark-promotion-gate-latest.md and %s/opscat-candidate-benchmark-promotion-gate.json\n' "$VERIFY_TMPDIR"
}


candidate_benchmark_regression_runner_smoke() {
  section "P56 candidate benchmark regression runner smoke"
  "${UV_DEV[@]}" python scripts/run_candidate_benchmark_regression_runner.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --repeat-count 3 \
    --output-json "$VERIFY_TMPDIR/opscat-candidate-benchmark-regression-runner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-candidate-benchmark-regression-runner.md" >/tmp/opscat-candidate-benchmark-regression-runner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-candidate-benchmark-regression-runner.md" /tmp/opscat-candidate-benchmark-regression-runner-latest.md
  printf 'Wrote /tmp/opscat-candidate-benchmark-regression-runner-latest.md and %s/opscat-candidate-benchmark-regression-runner.json\n' "$VERIFY_TMPDIR"
}

real_dataset_candidate_regression_bridge_smoke() {
  section "P57 real dataset candidate regression bridge smoke"
  "${UV_DEV[@]}" python scripts/run_real_dataset_candidate_regression_bridge.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
    --repeat-count 3 \
    --output-json "$VERIFY_TMPDIR/opscat-real-dataset-candidate-regression-bridge.json" \
    --output-md "$VERIFY_TMPDIR/opscat-real-dataset-candidate-regression-bridge.md" >/tmp/opscat-real-dataset-candidate-regression-bridge-latest.txt
  cp "$VERIFY_TMPDIR/opscat-real-dataset-candidate-regression-bridge.md" /tmp/opscat-real-dataset-candidate-regression-bridge-latest.md
  printf 'Wrote /tmp/opscat-real-dataset-candidate-regression-bridge-latest.md and %s/opscat-real-dataset-candidate-regression-bridge.json\n' "$VERIFY_TMPDIR"
}

llm_judgment_candidate_harness_smoke() {
  section "P58 LLM judgment candidate harness smoke"
  "${UV_DEV[@]}" python scripts/run_llm_judgment_candidate_harness.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
    --judgment-cases evals/judgment/seed/cases.json \
    --provider mock \
    --max-cases 4 \
    --output-json "$VERIFY_TMPDIR/opscat-llm-judgment-candidate-harness.json" \
    --output-md "$VERIFY_TMPDIR/opscat-llm-judgment-candidate-harness.md" >/tmp/opscat-llm-judgment-candidate-harness-latest.txt
  cp "$VERIFY_TMPDIR/opscat-llm-judgment-candidate-harness.md" /tmp/opscat-llm-judgment-candidate-harness-latest.md
  printf 'Wrote /tmp/opscat-llm-judgment-candidate-harness-latest.md and %s/opscat-llm-judgment-candidate-harness.json\n' "$VERIFY_TMPDIR"
}

hybrid_commander_comparator_smoke() {
  section "P59 hybrid commander comparator smoke"
  "${UV_DEV[@]}" python scripts/run_hybrid_commander_comparator.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
    --judgment-cases evals/judgment/seed/cases.json \
    --max-cases 4 \
    --output-json "$VERIFY_TMPDIR/opscat-hybrid-commander-comparator.json" \
    --output-md "$VERIFY_TMPDIR/opscat-hybrid-commander-comparator.md" >/tmp/opscat-hybrid-commander-comparator-latest.txt
  cp "$VERIFY_TMPDIR/opscat-hybrid-commander-comparator.md" /tmp/opscat-hybrid-commander-comparator-latest.md
  printf 'Wrote /tmp/opscat-hybrid-commander-comparator-latest.md and %s/opscat-hybrid-commander-comparator.json\n' "$VERIFY_TMPDIR"
}

operator_replacement_readiness_gate_v2_smoke() {
  section "P60 operator replacement readiness gate v2 smoke"
  "${UV_DEV[@]}" python scripts/run_operator_replacement_readiness_gate_v2.py \
    --cases evals/investigator/p51_operator_judgment_benchmark_v2_cases.json \
    --manifest evals/real_datasets/external/p44_benchmark_matrix_manifest.json \
    --judgment-cases evals/judgment/seed/cases.json \
    --max-cases 4 \
    --output-json "$VERIFY_TMPDIR/opscat-operator-replacement-readiness-gate-v2.json" \
    --output-md "$VERIFY_TMPDIR/opscat-operator-replacement-readiness-gate-v2.md" >/tmp/opscat-operator-replacement-readiness-gate-v2-latest.txt
  cp "$VERIFY_TMPDIR/opscat-operator-replacement-readiness-gate-v2.md" /tmp/opscat-operator-replacement-readiness-gate-v2-latest.md
  printf 'Wrote /tmp/opscat-operator-replacement-readiness-gate-v2-latest.md and %s/opscat-operator-replacement-readiness-gate-v2.json\n' "$VERIFY_TMPDIR"
}

local_shadow_connector_validation_smoke() {
  section "P61 local shadow connector validation smoke"
  "${UV_DEV[@]}" python scripts/run_local_shadow_connector_validation.py \
    --source evals/shadow/p61_local_shadow_source.json \
    --output-json "$VERIFY_TMPDIR/opscat-local-shadow-connector-validation.json" \
    --output-md "$VERIFY_TMPDIR/opscat-local-shadow-connector-validation.md" >/tmp/opscat-local-shadow-connector-validation-latest.txt
  cp "$VERIFY_TMPDIR/opscat-local-shadow-connector-validation.md" /tmp/opscat-local-shadow-connector-validation-latest.md
  printf 'Wrote /tmp/opscat-local-shadow-connector-validation-latest.md and %s/opscat-local-shadow-connector-validation.json\n' "$VERIFY_TMPDIR"
}

staging_read_only_connector_contract_smoke() {
  section "P62 staging read-only connector contract smoke"
  "${UV_DEV[@]}" python scripts/run_staging_read_only_connector_contract.py \
    --manifest evals/staging/p62_staging_connector_contract.json \
    --output-json "$VERIFY_TMPDIR/opscat-staging-read-only-connector-contract.json" \
    --output-md "$VERIFY_TMPDIR/opscat-staging-read-only-connector-contract.md" >/tmp/opscat-staging-read-only-connector-contract-latest.txt
  cp "$VERIFY_TMPDIR/opscat-staging-read-only-connector-contract.md" /tmp/opscat-staging-read-only-connector-contract-latest.md
  printf 'Wrote /tmp/opscat-staging-read-only-connector-contract-latest.md and %s/opscat-staging-read-only-connector-contract.json\n' "$VERIFY_TMPDIR"
}

staging_live_read_only_preflight_smoke() {
  section "P63 staging live read-only preflight smoke"
  "${UV_DEV[@]}" python scripts/run_staging_live_read_only_preflight.py \
    --manifest evals/staging/p63_staging_live_preflight.json \
    --output-json "$VERIFY_TMPDIR/opscat-staging-live-read-only-preflight.json" \
    --output-md "$VERIFY_TMPDIR/opscat-staging-live-read-only-preflight.md" >/tmp/opscat-staging-live-read-only-preflight-latest.txt
  cp "$VERIFY_TMPDIR/opscat-staging-live-read-only-preflight.md" /tmp/opscat-staging-live-read-only-preflight-latest.md
  printf 'Wrote /tmp/opscat-staging-live-read-only-preflight-latest.md and %s/opscat-staging-live-read-only-preflight.json\n' "$VERIFY_TMPDIR"
}

audited_staging_transport_gate_smoke() {
  section "P64 audited staging transport gate smoke"
  "${UV_DEV[@]}" python scripts/run_audited_staging_transport_gate.py \
    --manifest evals/staging/p64_audited_credential_transport_gate.json \
    --output-json "$VERIFY_TMPDIR/opscat-audited-staging-transport-gate.json" \
    --output-md "$VERIFY_TMPDIR/opscat-audited-staging-transport-gate.md" >/tmp/opscat-audited-staging-transport-gate-latest.txt
  cp "$VERIFY_TMPDIR/opscat-audited-staging-transport-gate.md" /tmp/opscat-audited-staging-transport-gate-latest.md
  printf 'Wrote /tmp/opscat-audited-staging-transport-gate-latest.md and %s/opscat-audited-staging-transport-gate.json\n' "$VERIFY_TMPDIR"
}

real_staging_dry_attach_smoke() {
  section "P65 real staging dry attach smoke"
  "${UV_DEV[@]}" python scripts/run_real_staging_dry_attach.py \
    --manifest evals/staging/p65_real_staging_dry_attach.json \
    --output-json "$VERIFY_TMPDIR/opscat-real-staging-dry-attach.json" \
    --output-md "$VERIFY_TMPDIR/opscat-real-staging-dry-attach.md" >/tmp/opscat-real-staging-dry-attach-latest.txt
  cp "$VERIFY_TMPDIR/opscat-real-staging-dry-attach.md" /tmp/opscat-real-staging-dry-attach-latest.md
  printf 'Wrote /tmp/opscat-real-staging-dry-attach-latest.md and %s/opscat-real-staging-dry-attach.json\n' "$VERIFY_TMPDIR"
}

autonomous_day_loop_backlog_smoke() {
  section "P66 autonomous day loop backlog smoke"
  "${UV_DEV[@]}" python scripts/run_autonomous_day_loop_backlog.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --output-json "$VERIFY_TMPDIR/opscat-autonomous-day-loop-backlog.json" \
    --output-md "$VERIFY_TMPDIR/opscat-autonomous-day-loop-backlog.md" >/tmp/opscat-autonomous-day-loop-backlog-latest.txt
  cp "$VERIFY_TMPDIR/opscat-autonomous-day-loop-backlog.md" /tmp/opscat-autonomous-day-loop-backlog-latest.md
  printf 'Wrote /tmp/opscat-autonomous-day-loop-backlog-latest.md and %s/opscat-autonomous-day-loop-backlog.json\n' "$VERIFY_TMPDIR"
}

autonomous_loop_executor_smoke() {
  section "P67 autonomous loop executor smoke"
  "${UV_DEV[@]}" python scripts/run_autonomous_loop_executor.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --mode local-auto \
    --max-tickets 3 \
    --output-json "$VERIFY_TMPDIR/opscat-autonomous-loop-executor.json" \
    --output-md "$VERIFY_TMPDIR/opscat-autonomous-loop-executor.md" >/tmp/opscat-autonomous-loop-executor-latest.txt
  cp "$VERIFY_TMPDIR/opscat-autonomous-loop-executor.md" /tmp/opscat-autonomous-loop-executor-latest.md
  printf 'Wrote /tmp/opscat-autonomous-loop-executor-latest.md and %s/opscat-autonomous-loop-executor.json\n' "$VERIFY_TMPDIR"
}

autonomous_agent_dispatcher_smoke() {
  section "P68 autonomous agent dispatcher smoke"
  "${UV_DEV[@]}" python scripts/run_autonomous_agent_dispatcher.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-tickets 3 \
    --max-parallel 2 \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-autonomous-agent-dispatcher-packets" \
    --output-json "$VERIFY_TMPDIR/opscat-autonomous-agent-dispatcher.json" \
    --output-md "$VERIFY_TMPDIR/opscat-autonomous-agent-dispatcher.md" >/tmp/opscat-autonomous-agent-dispatcher-latest.txt
  cp "$VERIFY_TMPDIR/opscat-autonomous-agent-dispatcher.md" /tmp/opscat-autonomous-agent-dispatcher-latest.md
  printf 'Wrote /tmp/opscat-autonomous-agent-dispatcher-latest.md and %s/opscat-autonomous-agent-dispatcher.json\n' "$VERIFY_TMPDIR"
}

autonomous_worker_runner_smoke() {
  section "P69 autonomous worker runner smoke"
  "${UV_DEV[@]}" python scripts/run_autonomous_worker_runner.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-tickets 3 \
    --max-parallel 2 \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-autonomous-worker-runner-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-autonomous-worker-runner-state.json" \
    --output-json "$VERIFY_TMPDIR/opscat-autonomous-worker-runner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-autonomous-worker-runner.md" >/tmp/opscat-autonomous-worker-runner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-autonomous-worker-runner.md" /tmp/opscat-autonomous-worker-runner-latest.md
  printf 'Wrote /tmp/opscat-autonomous-worker-runner-latest.md and %s/opscat-autonomous-worker-runner.json\n' "$VERIFY_TMPDIR"
}

gated_worker_process_runner_smoke() {
  section "P70 gated worker process runner smoke"
  "${UV_DEV[@]}" python scripts/run_gated_worker_process_runner.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-tickets 3 \
    --max-parallel 2 \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-gated-worker-process-runner-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-gated-worker-process-runner-state.json" \
    --output-json "$VERIFY_TMPDIR/opscat-gated-worker-process-runner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-gated-worker-process-runner.md" >/tmp/opscat-gated-worker-process-runner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-gated-worker-process-runner.md" /tmp/opscat-gated-worker-process-runner-latest.md
  printf 'Wrote /tmp/opscat-gated-worker-process-runner-latest.md and %s/opscat-gated-worker-process-runner.json\n' "$VERIFY_TMPDIR"
}

supervised_worker_execution_harness_smoke() {
  section "P71 supervised worker execution harness smoke"
  "${UV_DEV[@]}" python scripts/run_supervised_worker_execution_harness.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-tickets 3 \
    --max-parallel 2 \
    --enable-process-execution \
    --transport simulated \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-supervised-worker-execution-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-supervised-worker-execution-state.json" \
    --artifact-dir "$VERIFY_TMPDIR/opscat-supervised-worker-execution-artifacts" \
    --output-json "$VERIFY_TMPDIR/opscat-supervised-worker-execution-harness.json" \
    --output-md "$VERIFY_TMPDIR/opscat-supervised-worker-execution-harness.md" >/tmp/opscat-supervised-worker-execution-harness-latest.txt
  cp "$VERIFY_TMPDIR/opscat-supervised-worker-execution-harness.md" /tmp/opscat-supervised-worker-execution-harness-latest.md
  printf 'Wrote /tmp/opscat-supervised-worker-execution-harness-latest.md and %s/opscat-supervised-worker-execution-harness.json\n' "$VERIFY_TMPDIR"
}

stateful_all_day_loop_orchestrator_smoke() {
  section "P72 stateful all-day loop orchestrator smoke"
  "${UV_DEV[@]}" python scripts/run_stateful_all_day_loop_orchestrator.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-cycles 3 \
    --max-tickets-per-cycle 3 \
    --max-parallel 2 \
    --enable-process-execution \
    --transport simulated \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-stateful-all-day-loop-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-stateful-all-day-loop-state.json" \
    --artifact-dir "$VERIFY_TMPDIR/opscat-stateful-all-day-loop-artifacts" \
    --output-json "$VERIFY_TMPDIR/opscat-stateful-all-day-loop-orchestrator.json" \
    --output-md "$VERIFY_TMPDIR/opscat-stateful-all-day-loop-orchestrator.md" >/tmp/opscat-stateful-all-day-loop-orchestrator-latest.txt
  cp "$VERIFY_TMPDIR/opscat-stateful-all-day-loop-orchestrator.md" /tmp/opscat-stateful-all-day-loop-orchestrator-latest.md
  printf 'Wrote /tmp/opscat-stateful-all-day-loop-orchestrator-latest.md and %s/opscat-stateful-all-day-loop-orchestrator.json\n' "$VERIFY_TMPDIR"
}

long_run_loop_controller_smoke() {
  section "P73 long-run loop controller smoke"
  "${UV_DEV[@]}" python scripts/run_long_run_loop_controller.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-windows 2 \
    --p72-cycles-per-window 2 \
    --max-tickets-per-cycle 3 \
    --max-parallel 2 \
    --duration-seconds 10000 \
    --sleep-seconds 0 \
    --simulated-window-seconds 60 \
    --enable-process-execution \
    --transport simulated \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-long-run-loop-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-long-run-loop-state.json" \
    --artifact-dir "$VERIFY_TMPDIR/opscat-long-run-loop-artifacts" \
    --output-json "$VERIFY_TMPDIR/opscat-long-run-loop-controller.json" \
    --output-md "$VERIFY_TMPDIR/opscat-long-run-loop-controller.md" >/tmp/opscat-long-run-loop-controller-latest.txt
  cp "$VERIFY_TMPDIR/opscat-long-run-loop-controller.md" /tmp/opscat-long-run-loop-controller-latest.md
  printf 'Wrote /tmp/opscat-long-run-loop-controller-latest.md and %s/opscat-long-run-loop-controller.json\n' "$VERIFY_TMPDIR"
}

real_subprocess_execution_dry_run_gate_smoke() {
  section "P74 real subprocess execution dry-run gate smoke"
  "${UV_DEV[@]}" python scripts/run_real_subprocess_execution_dry_run_gate.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-tickets 3 \
    --max-parallel 2 \
    --max-processes 2 \
    --enable-real-subprocess \
    --git-status clean \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-real-subprocess-dry-run-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-real-subprocess-dry-run-state.json" \
    --artifact-dir "$VERIFY_TMPDIR/opscat-real-subprocess-dry-run-artifacts" \
    --output-json "$VERIFY_TMPDIR/opscat-real-subprocess-dry-run-gate.json" \
    --output-md "$VERIFY_TMPDIR/opscat-real-subprocess-dry-run-gate.md" >/tmp/opscat-real-subprocess-dry-run-gate-latest.txt
  cp "$VERIFY_TMPDIR/opscat-real-subprocess-dry-run-gate.md" /tmp/opscat-real-subprocess-dry-run-gate-latest.md
  printf 'Wrote /tmp/opscat-real-subprocess-dry-run-gate-latest.md and %s/opscat-real-subprocess-dry-run-gate.json\n' "$VERIFY_TMPDIR"
}

local_safe_subprocess_runner_smoke() {
  section "P75 local safe subprocess runner smoke"
  "${UV_DEV[@]}" python scripts/run_local_safe_subprocess_runner.py \
    --manifest evals/planning/p66_autonomous_day_loop_backlog.json \
    --completed P65 \
    --max-tickets 3 \
    --max-parallel 2 \
    --max-processes 2 \
    --enable-real-subprocess \
    --enable-local-subprocess \
    --git-status clean \
    --transport simulated \
    --dispatch-dir "$VERIFY_TMPDIR/opscat-local-safe-subprocess-dispatch" \
    --state-path "$VERIFY_TMPDIR/opscat-local-safe-subprocess-state.json" \
    --artifact-dir "$VERIFY_TMPDIR/opscat-local-safe-subprocess-artifacts" \
    --output-json "$VERIFY_TMPDIR/opscat-local-safe-subprocess-runner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-local-safe-subprocess-runner.md" >/tmp/opscat-local-safe-subprocess-runner-latest.txt
  cp "$VERIFY_TMPDIR/opscat-local-safe-subprocess-runner.md" /tmp/opscat-local-safe-subprocess-runner-latest.md
  printf 'Wrote /tmp/opscat-local-safe-subprocess-runner-latest.md and %s/opscat-local-safe-subprocess-runner.json\n' "$VERIFY_TMPDIR"
}

causal_remediation_benchmark_smoke() {
  section "P97 causal remediation benchmark smoke"
  "${UV_DEV[@]}" python scripts/run_causal_remediation_benchmark.py \
    --max-cases 12 \
    --seeds 11 \
    --output-json "$VERIFY_TMPDIR/opscat-p97-causal-remediation.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p97-causal-remediation.md" >/tmp/opscat-p97-causal-remediation-latest.txt
  cp "$VERIFY_TMPDIR/opscat-p97-causal-remediation.md" /tmp/opscat-p97-causal-remediation-latest.md
  printf 'Wrote /tmp/opscat-p97-causal-remediation-latest.md and %s/opscat-p97-causal-remediation.json\n' "$VERIFY_TMPDIR"
}

selector_comparison_smoke() {
  section "P98 selector comparison smoke"
  "${UV_DEV[@]}" python scripts/run_selector_comparison.py \
    --max-cases 12 \
    --seeds 11 \
    --output-json "$VERIFY_TMPDIR/opscat-p98-selector-comparison.json" >/tmp/opscat-p98-selector-comparison-latest.txt
  printf 'Wrote /tmp/opscat-p98-selector-comparison-latest.txt and %s/opscat-p98-selector-comparison.json\n' "$VERIFY_TMPDIR"
}

operational_scenario_matrix_smoke() {
  section "P99 comprehensive operational scenario matrix smoke"
  "${UV_DEV[@]}" python scripts/run_operational_scenario_matrix.py \
    --max-cases 20 \
    --seeds 11 \
    --sample-size 5 \
    --output-json "$VERIFY_TMPDIR/opscat-p99-operational-matrix.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p99-operational-matrix.md" >/tmp/opscat-p99-operational-matrix-latest.txt
  cp "$VERIFY_TMPDIR/opscat-p99-operational-matrix.md" /tmp/opscat-p99-operational-matrix-latest.md
  printf 'Wrote /tmp/opscat-p99-operational-matrix-latest.md and %s/opscat-p99-operational-matrix.json\n' "$VERIFY_TMPDIR"
}

stateful_incident_investigator_smoke() {
  section "P100 stateful multi-step incident investigator smoke"
  "${UV_DEV[@]}" python scripts/run_stateful_incident_investigator.py \
    --max-cases 16 \
    --seeds 11 \
    --sample-size 5 \
    --max-steps 3 \
    --output-json "$VERIFY_TMPDIR/opscat-p100-stateful-investigator.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p100-stateful-investigator.md" >/tmp/opscat-p100-stateful-investigator-latest.txt
  cp "$VERIFY_TMPDIR/opscat-p100-stateful-investigator.md" /tmp/opscat-p100-stateful-investigator-latest.md
  printf 'Wrote /tmp/opscat-p100-stateful-investigator-latest.md and %s/opscat-p100-stateful-investigator.json\n' "$VERIFY_TMPDIR"
}

tool_investigation_benchmark_smoke() {
  section "P101 tool-using hypothesis investigator smoke"
  "${UV_DEV[@]}" python scripts/run_tool_investigation_benchmark.py \
    --max-cases 16 --seeds 11 --sample-size 5 \
    --output-json "$VERIFY_TMPDIR/opscat-p101-tool-investigator.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p101-tool-investigator.md" >/tmp/opscat-p101-tool-investigator-latest.txt
  printf 'Wrote /tmp/opscat-p101-tool-investigator-latest.txt and %s/opscat-p101-tool-investigator.json\n' "$VERIFY_TMPDIR"
}

llm_tool_planner_evaluation_smoke() {
  section "P102 LLM diagnostic tool planner evaluation smoke"
  "${UV_DEV[@]}" python scripts/run_llm_tool_planner_evaluation.py \
    --max-cases 12 \
    --output-json "$VERIFY_TMPDIR/opscat-p102-llm-tool-planner.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p102-llm-tool-planner.md" >/tmp/opscat-p102-llm-tool-planner-latest.txt
  printf 'Wrote /tmp/opscat-p102-llm-tool-planner-latest.txt and %s/opscat-p102-llm-tool-planner.json\n' "$VERIFY_TMPDIR"
}

llm_diagnostic_episode_smoke() {
  section "P103 multi-step LLM diagnostic episode smoke"
  "${UV_DEV[@]}" python scripts/run_llm_diagnostic_episode.py \
    --max-cases 12 --obvious-only --seeds 11 --sample-size 5 \
    --max-tool-calls 3 --max-action-steps 3 \
    --output-json "$VERIFY_TMPDIR/opscat-p103-llm-diagnostic-episode.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p103-llm-diagnostic-episode.md" >/tmp/opscat-p103-llm-diagnostic-episode-latest.txt
  printf 'Wrote /tmp/opscat-p103-llm-diagnostic-episode-latest.txt and %s/opscat-p103-llm-diagnostic-episode.json\n' "$VERIFY_TMPDIR"
}

evidence_gap_investigator_smoke() {
  section "P104 evidence-gap investigator smoke"
  "${UV_DEV[@]}" python scripts/run_evidence_gap_investigator.py \
    --max-cases 10 --sample-size 10 --seeds 11 \
    --output-json "$VERIFY_TMPDIR/opscat-p104-evidence-gap-investigator.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p104-evidence-gap-investigator.md" >/tmp/opscat-p104-evidence-gap-investigator-latest.txt
  cp "$VERIFY_TMPDIR/opscat-p104-evidence-gap-investigator.md" /tmp/opscat-p104-evidence-gap-investigator-latest.md
  printf 'Wrote /tmp/opscat-p104-evidence-gap-investigator-latest.md and %s/opscat-p104-evidence-gap-investigator.json\n' "$VERIFY_TMPDIR"
}

p105_release_benchmark_smoke() {
  section "P105 release benchmark smoke"
  set +e
  "${UV_DEV[@]}" python scripts/run_failure_forecast_benchmark.py \
    --release-benchmark evals/proactive/forecast/p105_release_benchmark_rows.json \
    --output-json "$VERIFY_TMPDIR/opscat-p105-release-benchmark-smoke.json" >/tmp/opscat-p105-release-benchmark-smoke-latest.json
  p105_status=$?
  set -e
  if [[ "$p105_status" -ne 1 ]]; then
    printf 'Expected P105 smoke fixture to keep P106 locked with exit 1, got %s\n' "$p105_status" >&2
    exit 1
  fi
  python3 -c "import json, sys; p=json.load(open(sys.argv[1])); assert p['release_gate']['p106_unlocked'] is False" "$VERIFY_TMPDIR/opscat-p105-release-benchmark-smoke.json"
  cp "$VERIFY_TMPDIR/opscat-p105-release-benchmark-smoke.json" /tmp/opscat-p105-release-benchmark-smoke-latest.json
  printf 'Wrote /tmp/opscat-p105-release-benchmark-smoke-latest.json and %s/opscat-p105-release-benchmark-smoke.json\n' "$VERIFY_TMPDIR"
}

p106_preventive_action_benchmark_smoke() (
  section "P106 preventive action benchmark smoke"
  p106_fixture_dir="$(mktemp -d "$VERIFY_TMPDIR/p106-p105-release.XXXXXX")"
  cleanup_p106_fixture() {
    rm -rf -- "$p106_fixture_dir"
  }
  trap cleanup_p106_fixture EXIT INT TERM
  p105_artifact="$("${UV_DEV[@]}" python scripts/extract_p105_release_fixture.py \
    evals/prevention/p105_release_qualified_real_derived.tar.gz \
    6aaf35285f03cc7fe68b036a8172dba1615d1e5131939b2d8ef26787dd5c7342 \
    "$p106_fixture_dir")"
  "${UV_DEV[@]}" python scripts/run_preventive_action_benchmark.py \
    --cases evals/prevention/p106_benchmark_cases.json \
    --p105-artifact "$p105_artifact" \
    --output-json "$VERIFY_TMPDIR/opscat-p106-preventive-action-benchmark.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p106-preventive-action-benchmark.md" >/tmp/opscat-p106-preventive-action-benchmark-latest.json
  python3 -c "import json, sys; p=json.load(open(sys.argv[1])); assert p['scored'] is True; assert p['eligible_planner_evaluation_count'] == 1; assert p['planner_regret'] == 0.0; assert p['harmful_action_rate'] == 0.0; assert p['safe_fallback_rate'] == 1.0; assert p['policy_fail_closed_rate'] == 1.0; assert p['mutation_shaped_simulation_only_count'] == 1; assert p['authority'] == {'auth_enabled': False, 'production_mutation_enabled': False, 'action_authority': False, 'remediation_execution_enabled': False, 'default_external_model_calls': 0}; assert p['execution_enabled'] is False; assert p['simulation_only'] is True; assert p['p107_required_for_execution'] is True" "$VERIFY_TMPDIR/opscat-p106-preventive-action-benchmark.json"
  cp "$VERIFY_TMPDIR/opscat-p106-preventive-action-benchmark.md" /tmp/opscat-p106-preventive-action-benchmark-latest.md
  printf 'Wrote /tmp/opscat-p106-preventive-action-benchmark-latest.md and %s/opscat-p106-preventive-action-benchmark.json\n' "$VERIFY_TMPDIR"
)

p107_release_profile_tests() {
  section "P107 release profile tests"
  "${UV_DEV[@]}" pytest -q "${P107_RELEASE_PROFILE_TESTS[@]}"
}

p107_prevention_canary_evidence_smoke() {
  section "P107 prevention canary evidence smoke"
  "${UV_DEV[@]}" python scripts/run_prevention_canary_evidence.py \
    --cases evals/prevention/p107_canary_cases.json \
    --output-json "$VERIFY_TMPDIR/opscat-p107-canary-evidence.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p107-canary-evidence.md" >/tmp/opscat-p107-canary-evidence-latest.json
  cp "$VERIFY_TMPDIR/opscat-p107-canary-evidence.md" /tmp/opscat-p107-canary-evidence-latest.md
  printf 'Wrote /tmp/opscat-p107-canary-evidence-latest.md and %s/opscat-p107-canary-evidence.json\n' "$VERIFY_TMPDIR"
}

p108_release_profile_tests() {
  section "P108 release profile tests"
  "${UV_DEV[@]}" pytest -q "${P108_RELEASE_PROFILE_TESTS[@]}"
}

p109_release_profile_tests() {
  section "P109 real operations benchmark release profile"
  "${UV_DEV[@]}" pytest -q "${P109_RELEASE_PROFILE_TESTS[@]}"
}

p110_release_profile_tests() {
  section "P110 labeled RCAEval benchmark release profile"
  "${UV_DEV[@]}" pytest -q "${P110_RELEASE_PROFILE_TESTS[@]}"
}

p111_release_profile_tests() {
  section "P111 evidence-driven RCA accuracy profile"
  "${UV_DEV[@]}" pytest -q "${P111_RELEASE_PROFILE_TESTS[@]}"
}

p112_release_profile_tests() {
  section "P112 cross-system RCA release profile"
  "${UV_DEV[@]}" pytest -q "${P112_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p112_*.py scripts/*p112*.py tests/test_p112_*.py
  "${UV_DEV[@]}" mypy app/services/p112_*.py scripts/*p112*.py
}

p113_release_profile_tests() {
  section "P113 decoupled fresh-blind RCA release profile"
  "${UV_DEV[@]}" pytest -q "${P113_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p112_re1_loader.py app/services/p113_*.py scripts/*p113*.py tests/test_p113_*.py
  "${UV_DEV[@]}" mypy app/services/p112_re1_loader.py app/services/p113_*.py scripts/*p113*.py
}

p114_release_profile_tests() {
  section "P114 evidence adjudication development profile"
  "${UV_DEV[@]}" pytest -q "${P114_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p114_*.py scripts/*p114*.py tests/test_p114_*.py
  "${UV_DEV[@]}" mypy app/services/p114_*.py scripts/*p114*.py
}

p115_release_profile_tests() {
  section "P115 outcome-grounded remediation release profile"
  "${UV_DEV[@]}" pytest -q "${P115_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p115_*.py scripts/*p115*.py tests/test_p115_*.py
  "${UV_DEV[@]}" mypy app/services/p115_*.py scripts/*p115*.py
  section "P115 persisted release-evidence and transitive P116 freshness"
  "${UV_DEV[@]}" python scripts/validate_p115_release_evidence.py \
    evals/p115/release-evidence.json \
    --p116-import evals/p115/p116-release-evidence.json
}

p116_release_profile_tests() {
  section "P116 controlled fault-action lab release profile"
  "${UV_DEV[@]}" pytest -q "${P116_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p116_*.py scripts/*p116*.py tests/test_p116_*.py
  "${UV_DEV[@]}" mypy app/services/p116_*.py scripts/*p116*.py
  section "P116 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p116_release_evidence.py evals/p116/release-evidence.json
}

p117_release_profile_tests() {
  section "P117 evidence-bound action-selection release profile"
  "${UV_DEV[@]}" pytest -q "${P117_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p117_*.py scripts/*p117*.py tests/test_p117_*.py
  "${UV_DEV[@]}" mypy app/services/p117_*.py scripts/*p117*.py
  section "P117 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p117_release_evidence.py evals/p117/release-evidence.json
}

p118_release_profile_tests() {
  section "P118 local reactive-execution release profile"
  "${UV_DEV[@]}" pytest -q "${P118_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p118_*.py scripts/*p118*.py tests/test_p118_*.py
  "${UV_DEV[@]}" mypy app/services/p118_*.py scripts/*p118*.py
  section "P118 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p118_release_evidence.py evals/p118/release-evidence.json
}

p119_release_profile_tests() {
  section "P119 local closed-loop incident-response release profile"
  "${UV_DEV[@]}" pytest -q "${P119_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p119_*.py scripts/*p119*.py tests/test_p119_*.py
  "${UV_DEV[@]}" mypy app/services/p119_*.py scripts/*p119*.py
  section "P119 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p119_release_evidence.py evals/p119/release-evidence.json
}

p120_release_profile_tests() {
  section "P120 cross-system generalization release profile"
  "${UV_DEV[@]}" pytest -q "${P120_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p120_*.py scripts/*p120*.py tests/test_p120_*.py
  "${UV_DEV[@]}" mypy app/services/p120_*.py scripts/*p120*.py
  section "P120 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p120_release_evidence.py evals/p120/release-evidence.json
}

p121_release_profile_tests() {
  section "P121 proactive prevention release profile"
  "${UV_DEV[@]}" pytest -q "${P121_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p121_*.py scripts/*p121*.py tests/test_p121_*.py
  "${UV_DEV[@]}" mypy app/services/p121_*.py scripts/*p121*.py
  section "P121 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p121_release_evidence.py evals/p121/release-evidence.json
}

p122_release_profile_tests() {
  section "P122 open-source release-candidate profile"
  "${UV_DEV[@]}" pytest -q "${P122_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/cli.py app/plugin_sdk.py app/public_contracts.py app/services/p122_*.py scripts/*p122*.py tests/test_p122_*.py
  "${UV_DEV[@]}" mypy app/cli.py app/plugin_sdk.py app/public_contracts.py app/services/p122_*.py scripts/*p122*.py
  section "P122 security, SBOM, and license gate"
  "${UV_DEV[@]}" python scripts/run_p122_security_gate.py
  section "P122 locked dependency vulnerability audit"
  "${UV_DEV[@]}" python scripts/run_p122_vulnerability_audit.py --validate-only
  section "P122 docs and migration verification"
  "${UV_DEV[@]}" python scripts/verify_p122_docs.py
  "${UV_DEV[@]}" python scripts/verify_p122_migration_compatibility.py --workdir "$VERIFY_TMPDIR/p122-migration" --output "$VERIFY_TMPDIR/p122-migration.json"
  section "P122 promoted 1000-iteration performance soak"
  "${UV_DEV[@]}" python scripts/run_p122_performance_soak.py \
    --iterations 1000 \
    --workdir "$VERIFY_TMPDIR/p122-performance-soak" \
    --output "$VERIFY_TMPDIR/p122-performance-soak.json" \
    --compare-report evals/p122/performance-soak.json
  section "P122 package artifact checksums"
  "${UV_DEV[@]}" python scripts/verify_p122_reproducible_build.py --validate-only
  "${UV_DEV[@]}" python scripts/verify_p122_clean_install.py --validate-only
  "${UV_DEV[@]}" python - <<'PY'
import hashlib, json
from pathlib import Path
expected = json.loads(Path("evals/p122/package-checksums.json").read_text())
actual = {name: "sha256:" + hashlib.sha256((Path("dist") / name).read_bytes()).hexdigest() for name in expected}
if actual != expected:
    raise SystemExit("package artifact checksum mismatch")
print(json.dumps(actual, sort_keys=True))
PY
  section "P122 persisted release-evidence freshness"
  "${UV_DEV[@]}" python scripts/validate_p122_release_evidence.py evals/p122/release-evidence.json
}

phase_release_profile() {
  local phase="$1"
  shift
  local service_glob="app/services/${phase}_*.py"
  local script_glob="scripts/*${phase}*.py"
  local test_glob="tests/test_${phase}_*.py"
  local phase_label
  phase_label="$(printf '%s' "$phase" | tr '[:lower:]' '[:upper:]')"
  section "$phase_label evidence-qualified release profile"
  "${UV_DEV[@]}" pytest -q "$@"
  # The globs intentionally expand here so missing phase surfaces fail loudly.
  # shellcheck disable=SC2086
  "${UV_DEV[@]}" ruff check $service_glob $script_glob $test_glob
  # shellcheck disable=SC2086
  "${UV_DEV[@]}" mypy $service_glob $script_glob
}

p123_release_profile_tests() {
  phase_release_profile p123 "${P123_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" python scripts/run_p123_shadow_attachment.py \
    --manifest evals/p123/input/manifest.json \
    --output evals/p123/shadow-report.json \
    --release-evidence evals/p123/release-evidence.json
}
p124_release_profile_tests() {
  phase_release_profile p124 "${P124_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" python scripts/run_p124_judgment_quality.py \
    --cases evals/p124/input/cases.json \
    --output evals/p124/quality-report.json \
    --release-evidence evals/p124/release-evidence.json
}
p125_release_profile_tests() { phase_release_profile p125 "${P125_RELEASE_PROFILE_TESTS[@]}"; "${UV_DEV[@]}" python scripts/run_p125_shadow_resilience.py; }
p126_release_profile_tests() { phase_release_profile p126 "${P126_RELEASE_PROFILE_TESTS[@]}"; "${UV_DEV[@]}" python scripts/run_p126_lab_remediation.py; }
p127_release_profile_tests() { phase_release_profile p127 "${P127_RELEASE_PROFILE_TESTS[@]}"; "${UV_DEV[@]}" python scripts/run_p127_chaos_validation.py; }
p128_release_profile_tests() { phase_release_profile p128 "${P128_RELEASE_PROFILE_TESTS[@]}"; "${UV_DEV[@]}" python scripts/run_p128_operator_beta.py; }
p129_release_profile_tests() { phase_release_profile p129 "${P129_RELEASE_PROFILE_TESTS[@]}"; "${UV_DEV[@]}" python scripts/run_p129_distribution_maturity.py; }
p130_release_profile_tests() {
  phase_release_profile p130 "${P130_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" python scripts/build_p130_public_beta.py
  "${UV_DEV[@]}" python scripts/validate_p130_public_beta.py evals/p130/release-evidence.json
}
p131_release_profile_tests() {
  phase_release_profile p131 "${P131_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/monitor_cli.py app/api/health.py app/config.py
  "${UV_DEV[@]}" mypy app/monitor_cli.py app/api/health.py app/config.py
  "${UV_DEV[@]}" python scripts/run_p131_always_on_monitor.py
}
p132_release_profile_tests() {
  phase_release_profile p132 "${P132_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p131_always_on_monitor.py app/monitor_cli.py
  "${UV_DEV[@]}" mypy app/services/p131_always_on_monitor.py app/monitor_cli.py
  "${UV_DEV[@]}" python scripts/run_p132_supervised_runtime.py --output-dir "$VERIFY_TMPDIR/p132-release"
}
p133_release_profile_tests() {
  phase_release_profile p133 "${P133_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p131_always_on_monitor.py app/services/p132_supervised_runtime.py app/services/p133_deadman_outbox.py app/services/p133_release_evidence.py app/monitor_cli.py scripts/run_p133_deadman_outbox.py
  "${UV_DEV[@]}" mypy app/services/p131_always_on_monitor.py app/services/p132_supervised_runtime.py app/services/p133_deadman_outbox.py app/services/p133_release_evidence.py app/monitor_cli.py scripts/run_p133_deadman_outbox.py
  "${UV_DEV[@]}" python scripts/run_p133_deadman_outbox.py --output-dir "$VERIFY_TMPDIR/p133-release"
}
p134_release_profile_tests() {
  phase_release_profile p134 "${P134_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p134_observation_authority.py app/services/p134_release_evidence.py scripts/run_p134_observation_authority.py tests/test_p134_observation_authority.py tests/test_p134_release_evidence.py tests/test_p134_runner.py
  "${UV_DEV[@]}" mypy app/services/p134_observation_authority.py app/services/p134_release_evidence.py scripts/run_p134_observation_authority.py tests/test_p134_observation_authority.py tests/test_p134_release_evidence.py tests/test_p134_runner.py
  "${UV_DEV[@]}" python scripts/run_p134_observation_authority.py --output-dir "$VERIFY_TMPDIR/p134-release"
}
p135_release_profile_tests() {
  phase_release_profile p135 "${P135_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p135_provider_export_attachment.py app/services/p135_release_evidence.py scripts/run_p135_provider_export_attachment.py tests/test_p135_provider_export_attachment.py tests/test_p135_release_evidence.py tests/test_p135_runner.py
  "${UV_DEV[@]}" mypy app/services/p135_provider_export_attachment.py app/services/p135_release_evidence.py scripts/run_p135_provider_export_attachment.py tests/test_p135_provider_export_attachment.py tests/test_p135_release_evidence.py tests/test_p135_runner.py
  "${UV_DEV[@]}" python scripts/run_p135_provider_export_attachment.py --output-dir "$VERIFY_TMPDIR/p135-release"
}
p136_release_profile_tests() {
  phase_release_profile p136 "${P136_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check app/services/p136_incremental_observer.py app/services/p136_release_evidence.py app/services/p136_runner.py scripts/run_p136_incremental_observer.py tests/fixtures/p136/builders.py tests/test_p136_incremental_observer.py tests/test_p136_release_evidence.py tests/test_p136_runner.py
  "${UV_DEV[@]}" mypy app/services/p136_incremental_observer.py app/services/p136_release_evidence.py app/services/p136_runner.py scripts/run_p136_incremental_observer.py tests/test_p136_incremental_observer.py tests/test_p136_release_evidence.py tests/test_p136_runner.py
  "${UV_DEV[@]}" python scripts/run_p136_incremental_observer.py --output-dir "$VERIFY_TMPDIR/p136-release"
}
p137_release_profile_tests() {
  phase_release_profile p137 "${P137_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" ruff check \
    app/services/p137_contracts.py app/services/p137_p136_handoff.py \
    app/services/p137_correlation.py app/services/p137_hypotheses.py \
    app/services/p137_requests.py app/services/p137_classification.py \
    app/services/p137_ledger.py app/services/p137_runtime.py \
    app/services/p137_release_evidence.py app/services/p137_runner.py \
    scripts/run_p137_local_triage.py tests/fixtures/p137/builders.py \
    "${P137_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" mypy \
    app/services/p137_contracts.py app/services/p137_p136_handoff.py \
    app/services/p137_correlation.py app/services/p137_hypotheses.py \
    app/services/p137_requests.py app/services/p137_classification.py \
    app/services/p137_ledger.py app/services/p137_runtime.py \
    app/services/p137_release_evidence.py app/services/p137_runner.py \
    scripts/run_p137_local_triage.py tests/fixtures/p137/builders.py \
    tests/fixtures/p136/builders.py
  "${UV_DEV[@]}" python scripts/run_p137_local_triage.py \
    --mode final \
    --profile evals/p137/input/local-triage-profile.json \
    --canonical-matrix evals/p137/output/canonical-matrix.json \
    --freeze-manifest evals/p137/output/freeze-manifest.json \
    --final-implementation-review evals/p137/final-implementation-review.json \
    --output-dir "$VERIFY_TMPDIR/p137-release"
}
p138_release_profile_tests() {
  p136_release_profile_tests
  p137_release_profile_tests
  phase_release_profile p138 "${P138_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" python scripts/run_p138_observation_triage_supervisor.py \
    --mode final \
    --profile evals/p138/input/observation-triage-supervisor-profile.json \
    --canonical-matrix evals/p138/output/canonical-matrix.json \
    --freeze-manifest evals/p138/output/freeze-manifest.json \
    --final-implementation-review evals/p138/final-implementation-review.json \
    --output-dir "$VERIFY_TMPDIR/p138-release"
}
p139_release_profile_tests() {
  "${UV_DEV[@]}" python scripts/run_p136_incremental_observer.py \
    --profile evals/p136/input/incremental-observer-profile.json \
    --independent-review evals/p136/independent-review.json \
    --output-dir "$VERIFY_TMPDIR/p136-for-p139"
  "${UV_DEV[@]}" python scripts/run_p137_local_triage.py \
    --mode final \
    --profile evals/p137/input/local-triage-profile.json \
    --canonical-matrix evals/p137/output/canonical-matrix.json \
    --freeze-manifest evals/p137/output/freeze-manifest.json \
    --final-implementation-review evals/p137/final-implementation-review.json \
    --output-dir "$VERIFY_TMPDIR/p137-for-p139"
  "${UV_DEV[@]}" python scripts/run_p138_observation_triage_supervisor.py \
    --mode final \
    --profile evals/p138/input/observation-triage-supervisor-profile.json \
    --canonical-matrix evals/p138/output/canonical-matrix.json \
    --freeze-manifest evals/p138/output/freeze-manifest.json \
    --final-implementation-review evals/p138/final-implementation-review.json \
    --output-dir "$VERIFY_TMPDIR/p138-for-p139"
  phase_release_profile p139 "${P139_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" python scripts/run_p139_local_triage_service.py \
    --mode final \
    --profile evals/p139/input/local-triage-service-profile.json \
    --canonical-matrix evals/p139/output/canonical-matrix.json \
    --freeze-manifest evals/p139/output/freeze-manifest.json \
    --output-dir "$VERIFY_TMPDIR/p139-release" \
    --final-review evals/p139/final-implementation-review.json
}
p140_release_profile_tests() {
  p133_release_profile_tests
  p139_release_profile_tests
  phase_release_profile p140 "${P140_RELEASE_PROFILE_TESTS[@]}"
  "${UV_DEV[@]}" python scripts/run_p140_p139_deadman_adapter.py \
    --mode final \
    --profile evals/p140/input/p139-deadman-adapter-profile.json \
    --canonical-matrix evals/p140/output/canonical-matrix.json \
    --freeze-manifest evals/p140/output/freeze-manifest.json \
    --final-review evals/p140/final-implementation-review.json \
    --output-dir "$VERIFY_TMPDIR/p140-release"
}

p108_prevention_learning_evidence_smoke() {
  section "P108 prevention learning evidence smoke"
  "${UV_DEV[@]}" python scripts/run_prevention_learning_eval.py \
    --output-json "$VERIFY_TMPDIR/opscat-p108-learning-evidence.json" \
    --output-md "$VERIFY_TMPDIR/opscat-p108-learning-evidence.md" >/tmp/opscat-p108-learning-evidence-latest.json
  cp "$VERIFY_TMPDIR/opscat-p108-learning-evidence.md" /tmp/opscat-p108-learning-evidence-latest.md
  printf 'Wrote /tmp/opscat-p108-learning-evidence-latest.md and %s/opscat-p108-learning-evidence.json\n' "$VERIFY_TMPDIR"
}
commander_tournament() {
  section "P9 commander tournament"
  "${UV_DEV[@]}" python scripts/run_commander_tournament.py \
    --output-json "$VERIFY_TMPDIR/opscat-p9-commander-tournament.json" >/tmp/opscat-p9-commander-tournament-latest.json
  printf 'Wrote /tmp/opscat-p9-commander-tournament-latest.json and %s/opscat-p9-commander-tournament.json\n' "$VERIFY_TMPDIR"
}

replay_evals() {
  section "P7 replay eval runner"
  "${UV_DEV[@]}" python scripts/run_replay_evals.py \
    --output-json "$VERIFY_TMPDIR/opscat-replay-evals.json" \
    --output-md "$VERIFY_TMPDIR/opscat-replay-evals.md" >/tmp/opscat-replay-evals-latest.md
  printf 'Wrote /tmp/opscat-replay-evals-latest.md and %s/opscat-replay-evals.json\n' "$VERIFY_TMPDIR"
}

local_demo_smoke() {
  section "Local demo smoke"
  "${UV_DEV[@]}" python scripts/demo.py
}

agentic_demo_smoke() {
  section "P6 agentic demo smoke"
  "${UV_DEV[@]}" python scripts/demo_agentic_loop.py
}

workflow_cli_smoke() {
  section "Workflow CLI smoke"
  "${UV_DEV[@]}" python scripts/workflow_cli.py stats
}

docker_compose_config() {
  section "Docker Compose config"
  docker compose config >/tmp/opscat-compose-config.txt
  printf 'Wrote /tmp/opscat-compose-config.txt\n'
}

generated_artifact_scan() {
  section "Tracked generated artifact scan"
  tracked_generated="$({
    git ls-files '*__pycache__*' '*.py[co]' '.pytest_cache/*' '.ruff_cache/*' '.mypy_cache/*' 'opscat.db' 'opscat.egg-info/*' 2>/dev/null || true
  } | sed '/^$/d')"
  if [[ -n "$tracked_generated" ]]; then
    printf 'Tracked generated artifacts found:\n%s\n' "$tracked_generated" >&2
    exit 1
  fi
  printf 'No tracked generated artifacts found.\n'
}

whitespace_diff_check() {
  section "Whitespace diff check"
  git diff --check
}

docs_contract_tests() {
  section "Documentation contract tests"
  "${UV_DEV[@]}" pytest -q \
    tests/test_examples.py \
    tests/test_release_evidence_index.py \
    tests/test_ci_verification_profile.py \
    tests/test_oss_contributor_docs.py \
    tests/test_oss_quickstart_docs.py \
    tests/test_p6_release_evidence.py \
    tests/test_p6_security_review_docs.py \
    tests/test_agentic_demo.py \
    tests/test_p8_demo.py \
    tests/test_p8_security_docs.py \
    tests/test_p8_release_evidence.py \
    tests/test_p9_release_evidence.py \
    tests/test_p10_release_evidence.py \
    tests/test_p11_release_evidence.py \
    tests/test_p12_release_evidence.py \
    tests/test_p13_release_evidence.py \
    tests/test_p14_release_evidence.py \
    tests/test_p15_release_evidence.py \
    tests/test_p16_release_evidence.py \
    tests/test_p17_release_evidence.py \
    tests/test_p18a_release_evidence.py \
    tests/test_p18b_release_evidence.py \
    tests/test_p19_release_evidence.py \
    tests/test_p20_release_evidence.py \
    tests/test_p21_release_evidence.py \
    tests/test_p22_release_evidence.py \
    tests/test_p23_release_evidence.py \
    tests/test_p24_release_evidence.py \
    tests/test_p25_release_evidence.py \
    tests/test_p26_release_evidence.py \
    tests/test_p27_release_evidence.py \
    tests/test_p28_release_evidence.py \
    tests/test_p29_release_evidence.py \
    tests/test_p30_release_evidence.py \
    tests/test_p31_release_evidence.py \
    tests/test_p32_release_evidence.py \
    tests/test_p33_release_evidence.py \
    tests/test_p34_release_evidence.py \
    tests/test_p35_release_evidence.py \
    tests/test_p36_release_evidence.py \
    tests/test_p37_release_evidence.py \
    tests/test_p38_release_evidence.py \
    tests/test_p39_release_evidence.py \
    tests/test_p40_release_evidence.py \
    tests/test_p41_release_evidence.py \
    tests/test_p42_release_evidence.py \
    tests/test_p43_release_evidence.py \
    tests/test_p44_release_evidence.py \
    tests/test_p45_release_evidence.py \
    tests/test_p46_release_evidence.py \
    tests/test_p47_release_evidence.py \
    tests/test_p48_release_evidence.py \
    tests/test_p49_release_evidence.py \
    tests/test_p50_release_evidence.py \
    tests/test_p51_release_evidence.py \
    tests/test_p52_release_evidence.py \
    tests/test_p53_release_evidence.py \
    tests/test_p54_release_evidence.py \
    tests/test_p55_release_evidence.py \
    tests/test_p56_release_evidence.py \
    tests/test_p57_release_evidence.py \
    tests/test_p58_release_evidence.py \
    tests/test_p59_release_evidence.py \
    tests/test_p60_release_evidence.py \
    tests/test_p61_release_evidence.py \
    tests/test_p62_release_evidence.py \
    tests/test_p63_release_evidence.py \
    tests/test_p64_release_evidence.py \
    tests/test_p65_release_evidence.py \
    tests/test_p66_release_evidence.py \
    tests/test_p67_release_evidence.py \
    tests/test_p68_release_evidence.py \
    tests/test_p69_release_evidence.py \
    tests/test_p70_release_evidence.py \
    tests/test_p71_release_evidence.py \
    tests/test_p72_release_evidence.py \
    tests/test_p73_release_evidence.py \
    tests/test_p74_release_evidence.py \
    tests/test_p75_release_evidence.py \
    tests/test_p76_release_evidence.py \
    tests/test_p77_release_evidence.py \
    tests/test_p78_release_evidence.py \
    tests/test_p79_release_evidence.py \
    tests/test_p81_release_evidence.py \
    tests/test_p82_release_evidence.py \
    tests/test_p83_release_evidence.py \
    tests/test_p85_release_evidence.py \
    tests/test_p86_release_evidence.py \
    tests/test_p87_release_evidence.py \
    tests/test_p88_release_evidence.py \
    tests/test_p89_release_evidence.py \
    tests/test_p90_release_evidence.py \
    tests/test_p91_release_evidence.py \
    tests/test_p92_release_evidence.py \
    tests/test_p93_release_evidence.py \
    tests/test_p94_release_evidence.py \
    tests/test_p95_release_evidence.py \
    tests/test_p96_release_evidence.py \
    tests/test_p97_release_evidence.py \
    tests/test_p98_release_evidence.py \
    tests/test_p99_release_evidence.py \
    tests/test_p100_release_evidence.py \
    tests/test_p101_release_evidence.py \
    tests/test_p102_release_evidence.py \
    tests/test_p103_release_evidence.py \
    tests/test_evidence_gap_investigator.py \
    tests/test_p104_release_evidence.py \
    tests/test_failure_forecast_engine.py \
    tests/test_p105_release_evidence.py \
    tests/test_p106_release_evidence.py \
    tests/test_p107_release_evidence.py \
    tests/test_p108_release_evidence.py
}

run_fast() {
  compile_check
  lint_check
  type_check
  pytest_suite
}

run_eval() {
  golden_evals
  connector_evals
  agentic_evals
  replay_evals
  commander_tournament
  judgment_benchmark
  corpus_audit
  real_dataset_eval
  llm_context_smoke
  llm_judgment_smoke
  llm_provider_eval_smoke
  policy_calibration_smoke
  realtime_source_replay_smoke
  model_quality_lab_smoke
  operator_improvement_loop_smoke
  closed_loop_response_smoke
  runtime_loop_smoke
  night_shift_drill_smoke
  proactive_risk_sentinel_smoke
  proactive_calibration_smoke
  telemetry_adapter_smoke
  connector_readiness_smoke
  read_only_polling_smoke
  telemetry_judgment_quality_smoke
  controlled_remediation_smoke
  operator_replacement_drill_smoke
  real_telemetry_replay_smoke
  live_connector_dry_run_smoke
  read_only_polling_v2_smoke
  incident_shadow_mode_smoke
  approval_control_plane_smoke
  open_source_config_hardening_smoke
  agent_evaluation_dashboard_smoke
  runbook_learning_loop_smoke
  production_readiness_milestone_smoke
  raw_real_dataset_replay_smoke
  external_dataset_acquisition_smoke
  public_dataset_benchmark_smoke
  public_dataset_matrix_smoke
  evidence_grounded_judgment_smoke
  evidence_sufficiency_gate_v2_smoke
  investigator_loop_smoke
  tool_selection_planner_smoke
  hypothesis_reranker_smoke
  remediation_verification_loop_smoke
  recovery_proof_engine_smoke
  runbook_simulation_tournament_smoke
  action_sandbox_hardening_smoke
  approval_automation_policy_lab_smoke
  rollback_pr_draft_automation_smoke
  slack_ticket_draft_automation_smoke
  post_action_outcome_monitor_smoke
  outcome_driven_next_action_planner_smoke
  local_autonomous_supervisor_loop_smoke
  resumable_local_supervisor_runner_smoke
  supervisor_run_report_artifact_smoke
  bounded_local_supervisor_scheduler_smoke
  safe_local_auto_run_entrypoint_smoke
  safe_auto_run_readiness_gate_smoke
  readiness_gap_remediation_planner_smoke
  operator_replacement_acceptance_drill_v3_smoke
  portfolio_demo_pack_smoke
  operator_transcript_demo_smoke
  night_operator_drill_v2_smoke
  operator_judgment_benchmark_v2_smoke
  failure_mining_loop_smoke
  failure_driven_improvement_pack_smoke
  failure_driven_benchmark_improvement_smoke
  candidate_benchmark_promotion_gate_smoke
  candidate_benchmark_regression_runner_smoke
  real_dataset_candidate_regression_bridge_smoke
  llm_judgment_candidate_harness_smoke
  hybrid_commander_comparator_smoke
  operator_replacement_readiness_gate_v2_smoke
  local_shadow_connector_validation_smoke
  staging_read_only_connector_contract_smoke
  staging_live_read_only_preflight_smoke
  audited_staging_transport_gate_smoke
  real_staging_dry_attach_smoke
  autonomous_day_loop_backlog_smoke
  autonomous_loop_executor_smoke
  autonomous_agent_dispatcher_smoke
  autonomous_worker_runner_smoke
  gated_worker_process_runner_smoke
  supervised_worker_execution_harness_smoke
  stateful_all_day_loop_orchestrator_smoke
  long_run_loop_controller_smoke
  real_subprocess_execution_dry_run_gate_smoke
  local_safe_subprocess_runner_smoke
  causal_remediation_benchmark_smoke
  selector_comparison_smoke
  operational_scenario_matrix_smoke
  stateful_incident_investigator_smoke
  tool_investigation_benchmark_smoke
  llm_tool_planner_evaluation_smoke
  llm_diagnostic_episode_smoke
  evidence_gap_investigator_smoke
  p105_release_benchmark_smoke
  p106_preventive_action_benchmark_smoke
  p107_prevention_canary_evidence_smoke
  p108_prevention_learning_evidence_smoke
}

run_docs() {
  docs_contract_tests
  p107_release_profile_tests
  p108_release_profile_tests
  p109_release_profile_tests
  generated_artifact_scan
  whitespace_diff_check
}

run_p107_release() {
  p107_release_profile_tests
  p107_prevention_canary_evidence_smoke
}

run_p108_release() {
  p108_release_profile_tests
  p108_prevention_learning_evidence_smoke
}

run_p109_release() {
  p109_release_profile_tests
}

run_p110_release() {
  p110_release_profile_tests
}

run_p111_release() {
  p111_release_profile_tests
  local p111_root="evals/real_datasets/external/p111/results/blind"
  if [[ -f "$p111_root/freeze-manifest.json" && -f "$p111_root/baseline/final/candidate-nvidia.json" && -f "$p111_root/candidate-run1/final/candidate-nvidia.json" && -f "$p111_root/candidate-run2/final/candidate-nvidia.json" ]]; then
    section "P111 sealed blind artifact replay and release gates"
    "${UV_DEV[@]}" python scripts/build_p111_release_evidence.py \
      --freeze-manifest "$p111_root/freeze-manifest.json" \
      --baseline "$p111_root/baseline/final/candidate-nvidia.json" \
      --candidate "$p111_root/candidate-run1/final/candidate-nvidia.json" \
      --repeat "$p111_root/candidate-run2/final/candidate-nvidia.json" \
      --output-dir "$VERIFY_TMPDIR/p111-release"
  fi
}

run_p112_release() {
  p112_release_profile_tests
  local p112_root="evals/real_datasets/external/p112/results/blind"
  if [[ -f "$p112_root/freeze/freeze-manifest.json" && -f "$p112_root/baseline/final/candidate-nvidia.json" && -f "$p112_root/candidate-run1/final/candidate-nvidia.json" && -f "$p112_root/candidate-run2/final/candidate-nvidia.json" ]]; then
    section "P112 sealed blind artifact replay and release gates"
    "${UV_DEV[@]}" python scripts/build_p112_release_evidence.py \
      --freeze-dir "$p112_root/freeze" \
      --baseline "$p112_root/baseline/final/candidate-nvidia.json" \
      --candidate "$p112_root/candidate-run1/final/candidate-nvidia.json" \
      --repeat "$p112_root/candidate-run2/final/candidate-nvidia.json" \
      --output-dir "$VERIFY_TMPDIR/p112-release"
  fi
}

run_p113_release() {
  p113_release_profile_tests
  local p113_root="evals/real_datasets/external/p113/results/blind"
  if [[ -f "$p113_root/acquisition-verification.json" && -f "$p113_root/freeze/freeze-manifest.json" && -f "$p113_root/diagnosis/p113-diagnosis-evaluation.json" ]]; then
    section "P113 sealed blind artifact replay and fail-closed release gates"
    "${UV_DEV[@]}" python scripts/build_p113_release_evidence.py \
      --acquisition-verification "$p113_root/acquisition-verification.json" \
      --freeze-manifest "$p113_root/freeze/freeze-manifest.json" \
      --packet-manifest "$p113_root/freeze/packet-hash-manifest.json" \
      --p112-baseline-evaluation "$p113_root/diagnosis/p112-baseline-evaluation.json" \
      --diagnosis-evaluation "$p113_root/diagnosis/p113-diagnosis-evaluation.json" \
      --diagnosis-contract-evaluation "$p113_root/diagnosis/p113-diagnosis-contract-evaluation.json" \
      --output "$VERIFY_TMPDIR/p113-release.json" \
      --markdown-output "$VERIFY_TMPDIR/p113-release.md"
  fi
}

run_p114_release() {
  p114_release_profile_tests
}

run_p115_release() {
  p115_release_profile_tests
}

run_p116_release() {
  p116_release_profile_tests
}

run_p117_release() {
  p117_release_profile_tests
}

run_p118_release() {
  p118_release_profile_tests
}

run_p119_release() {
  p119_release_profile_tests
}

run_p120_release() {
  p120_release_profile_tests
}

run_p121_release() {
  p121_release_profile_tests
}

run_p122_release() {
  p122_release_profile_tests
}

run_p123_release() { p123_release_profile_tests; }
run_p124_release() { p124_release_profile_tests; }
run_p125_release() { p125_release_profile_tests; }
run_p126_release() { p126_release_profile_tests; }
run_p127_release() { p127_release_profile_tests; }
run_p128_release() { p128_release_profile_tests; }
run_p129_release() { p129_release_profile_tests; }
run_p130_release() { p130_release_profile_tests; }
run_p131_release() { p131_release_profile_tests; }
run_p132_release() { p132_release_profile_tests; }
run_p133_release() { p133_release_profile_tests; }
run_p134_release() { p134_release_profile_tests; }
run_p135_release() { p135_release_profile_tests; }
run_p136_release() { p136_release_profile_tests; }
run_p137_release() { p137_release_profile_tests; }
run_p138_release() { p138_release_profile_tests; }
run_p139_release() { p139_release_profile_tests; }
run_p140_release() { p140_release_profile_tests; }

run_full() {
  run_fast
  coverage_gate
  run_eval
  local_demo_smoke
  agentic_demo_smoke
  workflow_cli_smoke
  docker_compose_config
  generated_artifact_scan
  whitespace_diff_check
}

case "$VERIFY_PROFILE" in
  fast) run_fast ;;
  eval) run_eval ;;
  docs) run_docs ;;
  p107-release) run_p107_release ;;
  p108-release) run_p108_release ;;
  p109-release) run_p109_release ;;
  p110-release) run_p110_release ;;
  p111-release) run_p111_release ;;
  p112-release) run_p112_release ;;
  p113-release) run_p113_release ;;
  p114-release) run_p114_release ;;
  p115-release) run_p115_release ;;
  p116-release) run_p116_release ;;
  p117-release) run_p117_release ;;
  p118-release) run_p118_release ;;
  p119-release) run_p119_release ;;
  p120-release) run_p120_release ;;
  p121-release) run_p121_release ;;
  p122-release) run_p122_release ;;
  p123-release) run_p123_release ;;
  p124-release) run_p124_release ;;
  p125-release) run_p125_release ;;
  p126-release) run_p126_release ;;
  p127-release) run_p127_release ;;
  p128-release) run_p128_release ;;
  p129-release) run_p129_release ;;
  p130-release) run_p130_release ;;
  p131-release) run_p131_release ;;
  p132-release) run_p132_release ;;
  p133-release) run_p133_release ;;
  p134-release) run_p134_release ;;
  p135-release) run_p135_release ;;
  p136-release) run_p136_release ;;
  p137-release) run_p137_release ;;
  p138-release) run_p138_release ;;
  p139-release) run_p139_release ;;
  p140-release) run_p140_release ;;
  full) run_full ;;
esac

section "Verification complete ($VERIFY_PROFILE)"
