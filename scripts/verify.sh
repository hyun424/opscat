#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

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

section "Python bytecode compile"
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q app tests scripts

section "Ruff lint"
"${UV_DEV[@]}" ruff check app tests scripts

section "Mypy typecheck"
"${UV_DEV[@]}" mypy app tests scripts

section "Pytest regression suite"
"${UV_DEV[@]}" pytest -q

section "Coverage gate"
"${UV_DEV[@]}" python scripts/coverage_gate.py --json-output "$VERIFY_TMPDIR/coverage-summary.json"

section "Golden eval runner"
"${UV_DEV[@]}" python scripts/run_evals.py --output-json "$VERIFY_TMPDIR/opscat-evals.json" --output-md "$VERIFY_TMPDIR/opscat-evals.md" >/tmp/opscat-evals-latest.md
printf 'Wrote /tmp/opscat-evals-latest.md and %s/opscat-evals.json\n' "$VERIFY_TMPDIR"

section "Local demo smoke"
"${UV_DEV[@]}" python scripts/demo.py

section "Docker Compose config"
docker compose config >/tmp/opscat-compose-config.txt
printf 'Wrote /tmp/opscat-compose-config.txt\n'

section "Tracked generated artifact scan"
tracked_generated="$({
  git ls-files '*__pycache__*' '*.py[co]' '.pytest_cache/*' '.ruff_cache/*' '.mypy_cache/*' 'opscat.db' 'opscat.egg-info/*' 'uv.lock' 2>/dev/null || true
} | sed '/^$/d')"
if [[ -n "$tracked_generated" ]]; then
  printf 'Tracked generated artifacts found:\n%s\n' "$tracked_generated" >&2
  exit 1
fi
printf 'No tracked generated artifacts found.\n'

section "Whitespace diff check"
git diff --check

section "Verification complete"
