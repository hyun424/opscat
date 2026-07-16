#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/opscat-p159-p163-uv-cache}"
mkdir -p "$UV_CACHE_DIR"

sources=(
  app/services/p159_p163_live_operator_program.py
  scripts/run_p159_p163_qualification.py
  tests/test_p159_p163_live_operator_program.py
)

uv run --no-sync --extra dev pytest -q tests/test_p159_p163_live_operator_program.py
uv run --no-sync --extra dev ruff check "${sources[@]}"
uv run --no-sync --extra dev mypy "${sources[@]}"
bash -n scripts/verify_p159_p163.sh

coverage_dir="$(mktemp -d "${TMPDIR:-/tmp}/opscat-p159-p163-coverage.XXXXXX")"
uv run --no-sync --extra dev python -m trace \
  --count --missing --coverdir "$coverage_dir" \
  --module pytest -q tests/test_p159_p163_live_operator_program.py
uv run --no-sync --extra dev python - \
  "$coverage_dir/app.services.p159_p163_live_operator_program.cover" \
  app/services/p159_p163_live_operator_program.py <<'PY'
import ast
import re
import sys
from pathlib import Path

cover_path = Path(sys.argv[1])
source_path = Path(sys.argv[2])
covered_lines = set()
missed_lines = set()
for line_number, line in enumerate(cover_path.read_text(encoding="utf-8").splitlines(), start=1):
    if re.match(r"^\s*\d+:", line):
        covered_lines.add(line_number)
    elif line.startswith(">>>>>>"):
        missed_lines.add(line_number)
tree = ast.parse(source_path.read_text(encoding="utf-8"))
statement_lines = {node.lineno for node in ast.walk(tree) if isinstance(node, ast.stmt)}
measured = statement_lines & (covered_lines | missed_lines)
covered = len(statement_lines & covered_lines)
percent = 100.0 if not measured else covered * 100.0 / len(measured)
print(f"P159-P163 service coverage: {covered}/{len(measured)} lines ({percent:.1f}%)")
if percent < 80.0:
    raise SystemExit(f"P159-P163 coverage below 80%: {percent:.1f}%")
PY

for phase in p159 p160 p161 p162 p163; do
  for artifact in \
    "evals/$phase/output/report.json" \
    "evals/$phase/output/freeze-manifest.json" \
    "evals/$phase/final-implementation-review.json" \
    "evals/$phase/output/release-evidence.json"; do
    test -f "$artifact"
  done
  uv run --no-sync --extra dev python scripts/run_p159_p163_qualification.py "$phase" --mode validate >/dev/null
done

git diff --check
