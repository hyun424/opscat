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
    tests/test_p11_release_evidence.py
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
