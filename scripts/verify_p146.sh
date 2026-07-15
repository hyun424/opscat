#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/opscat-p146-uv-cache}"

P146_TESTS=(
  tests/test_p146_live_shadow.py
  tests/test_p146_release_evidence.py
  tests/test_p146_cli.py
  tests/test_p146_runner.py
)
P146_PY_SOURCES=(
  app/p146_live_shadow_cli.py
  app/services/p146_live_shadow.py
  app/services/p146_release_evidence.py
  app/services/p146_runner.py
  scripts/run_p146_live_shadow.py
  scripts/run_p146_release.py
  tests/fixtures/p146
  "${P146_TESTS[@]}"
)
P146_ARTIFACTS=(
  scripts/verify_p146.sh
  pyproject.toml
)

uv run --no-sync --extra dev pytest -q "${P146_TESTS[@]}"
uv run --no-sync --extra dev ruff check "${P146_PY_SOURCES[@]}"
uv run --no-sync --extra dev mypy "${P146_PY_SOURCES[@]}"
test -f app/services/p146_runner.py
test -f scripts/run_p146_release.py
test -f "${P146_ARTIFACTS[0]}"
uv run --no-sync --extra dev python -m app.p146_live_shadow_cli --help >/dev/null
uv run --no-sync --extra dev python -m scripts.run_p146_release --help >/dev/null
