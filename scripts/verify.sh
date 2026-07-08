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
Usage: bash scripts/verify.sh [--profile fast|full|eval|docs]

Profiles:
  fast  Compile, lint, typecheck, and pytest regression suite.
  full  Complete release gate, including coverage, evals, demos, Docker config, and hygiene checks.
  eval  Golden incident evals, connector evals, and P6 agentic-loop evals only.
  docs  Documentation/release evidence contract tests plus repo hygiene checks.
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
  fast|full|eval|docs) ;;
  *)
    printf 'Unknown verify profile: %s\n' "$VERIFY_PROFILE" >&2
    exit 2
    ;;
esac

section() {
  printf '\n==> %s\n' "$1"
}

UV_DEV=(uv run --no-sync --extra dev)
VERIFY_TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$VERIFY_TMPDIR"
}
trap cleanup EXIT
mkdir -p "$VERIFY_TMPDIR/reports"
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
    git ls-files '*__pycache__*' '*.py[co]' '.pytest_cache/*' '.ruff_cache/*' '.mypy_cache/*' 'opscat.db' 'opscat.egg-info/*' 'uv.lock' 2>/dev/null || true
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
    tests/test_p37_release_evidence.py
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
}

run_docs() {
  docs_contract_tests
  generated_artifact_scan
  whitespace_diff_check
}

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
  full) run_full ;;
esac

section "Verification complete ($VERIFY_PROFILE)"
