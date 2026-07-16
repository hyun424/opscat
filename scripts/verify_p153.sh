#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/opscat-p153-uv-cache}"
mkdir -p "$UV_CACHE_DIR"

selectors=(
  tests/test_p153_staging_shadow.py::test_contract_and_predecessor_fail_closed
  tests/test_p153_staging_shadow.py::test_happy_path_investigates_and_builds_grounded_judgment
  tests/test_p153_staging_shadow.py::test_missing_evidence_abstains_and_resume_is_deduplicated
  tests/test_p153_staging_shadow.py::test_live_boundary_redaction_and_budget_fail_closed
  tests/test_p153_staging_shadow.py::test_release_evidence_requires_zero_finding_review
)
sources=(
  app/services/p153_staging_shadow.py
  scripts/run_p153_staging_shadow.py
  tests/test_p153_staging_shadow.py
)

uv run --no-sync --extra dev pytest -q "${selectors[@]}"
uv run --no-sync --extra dev ruff check "${sources[@]}"
uv run --no-sync --extra dev mypy "${sources[@]}"
bash -n scripts/verify_p153.sh

coverage_dir="$(mktemp -d "${TMPDIR:-/tmp}/opscat-p153-coverage.XXXXXX")"
uv run --no-sync --extra dev python -m trace \
  --count --missing --coverdir "$coverage_dir" --module pytest -q "${selectors[@]}"
uv run --no-sync --extra dev python - \
  "$coverage_dir/app.services.p153_staging_shadow.cover" \
  app/services/p153_staging_shadow.py <<'PY'
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
print(f"P153 service coverage: {covered}/{len(measured)} lines ({percent:.1f}%)")
if percent < 80.0:
    raise SystemExit(f"P153 coverage below 80%: {percent:.1f}%")
PY

for artifact in \
  evals/p153/output/report.json \
  evals/p153/output/freeze-manifest.json \
  evals/p153/final-implementation-review.json \
  evals/p153/output/release-evidence.json; do
  test -f "$artifact"
done

output_dir="$(mktemp -d "${TMPDIR:-/tmp}/opscat-p153-final.XXXXXX")"
uv run --no-sync --extra dev python scripts/run_p153_staging_shadow.py final \
  --report evals/p153/output/report.json \
  --freeze-manifest evals/p153/output/freeze-manifest.json \
  --final-review evals/p153/final-implementation-review.json \
  --output-dir "$output_dir"
cmp evals/p153/output/release-evidence.json "$output_dir/release-evidence.json"
git diff --check
