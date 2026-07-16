#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/opscat-p147-p152-uv-cache}"
mkdir -p "$UV_CACHE_DIR"

phase="${1:-}"
case "$phase" in
  p147|p148|p149|p150|p151|p152) ;;
  *) printf 'usage: %s p147|p148|p149|p150|p151|p152\n' "$0" >&2; exit 2 ;;
esac

module=""
cli=""
case "$phase" in
  p147) module="p147_durable_shadow"; cli="scripts/run_p147_qualification.py" ;;
  p148) module="p148_reversible_lab"; cli="scripts/run_p148_qualification.py" ;;
  p149) module="p149_canary_control"; cli="scripts/run_p149_qualification.py" ;;
  p150) module="p150_unattended_soak"; cli="scripts/run_p150_qualification.py" ;;
  p151) module="p151_ground_truth_quality"; cli="scripts/run_p151_qualification.py" ;;
  p152) module="p152_operator_readiness"; cli="scripts/run_p152_qualification.py" ;;
esac

test_file="tests/test_${module}.py"
selectors=(
  "${test_file}::test_contract_and_predecessor_fail_closed"
  "${test_file}::test_happy_path_report_and_counters"
  "${test_file}::test_fault_matrix_and_recovery"
  "${test_file}::test_forgery_and_authority_rejected"
  "${test_file}::test_release_evidence_requires_zero_finding_review"
)
sources=(
  app/services/p147_p152_contracts.py
  "app/services/${module}.py"
  "$cli"
  "$test_file"
)
canonical_report="evals/${phase}/output/report.json"
canonical_freeze="evals/${phase}/output/freeze-manifest.json"
canonical_review="evals/${phase}/final-implementation-review.json"

require_canonical_final_artifacts() {
  local missing=0
  local artifact
  for artifact in "$canonical_report" "$canonical_freeze" "$canonical_review"; do
    if [[ ! -f "$artifact" || -L "$artifact" ]]; then
      printf 'missing required %s release artifact: %s\n' "$phase" "$artifact" >&2
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    exit 1
  fi
}

final_mode_smoke() {
  local output_dir
  output_dir="$(mktemp -d "${TMPDIR:-/tmp}/opscat-${phase}-final.XXXXXX")"
  case "$phase" in
    p147|p148|p149)
      uv run --no-sync --extra dev python "$cli" final \
        --report "$canonical_report" \
        --freeze-manifest "$canonical_freeze" \
        --final-review "$canonical_review" \
        --output-dir "$output_dir"
      ;;
    p150)
      uv run --no-sync --extra dev python "$cli" final \
        --report "$canonical_report" \
        --freeze-manifest "$canonical_freeze" \
        --final-review "$canonical_review" \
        --wall-clock-result "evals/p150/input/wall-clock-run/wall-clock-result.json" \
        --wall-clock-ledger "evals/p150/input/wall-clock-run/wall-clock-cycles.jsonl" \
        --wall-clock-checkpoint "evals/p150/input/wall-clock-run/wall-clock-checkpoint.json" \
        --output-dir "$output_dir"
      ;;
    p151|p152)
      uv run --no-sync --extra dev python "$cli" \
        --mode final \
        --review "$canonical_review" \
        --output-dir "$output_dir"
      cmp "$canonical_report" "$output_dir/report.json"
      cmp "$canonical_freeze" "$output_dir/freeze-manifest.json"
      ;;
  esac
  test -f "$output_dir/release-evidence.json"
}

coverage_gate() {
  local coverage_dir
  coverage_dir="$(mktemp -d "${TMPDIR:-/tmp}/opscat-${phase}-coverage.XXXXXX")"
  uv run --no-sync --extra dev python -m trace \
    --count \
    --missing \
    --coverdir "$coverage_dir" \
    --module pytest \
    -q \
    "${selectors[@]}"
  uv run --no-sync --extra dev python - "$coverage_dir/app.services.${module}.cover" "app/services/${module}.py" "$phase" <<'PY'
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

cover_path = Path(sys.argv[1])
source_path = Path(sys.argv[2])
phase = sys.argv[3].upper()
covered_lines = set()
missed_lines = set()
for line_number, line in enumerate(cover_path.read_text(encoding="utf-8").splitlines(), start=1):
    if re.match(r"^\s*\d+:", line):
        covered_lines.add(line_number)
    elif line.startswith(">>>>>>"):
        missed_lines.add(line_number)
tree = ast.parse(source_path.read_text(encoding="utf-8"))
statement_lines = {node.lineno for node in ast.walk(tree) if isinstance(node, ast.stmt)}
measured_lines = statement_lines & (covered_lines | missed_lines)
covered = len(statement_lines & covered_lines)
total = len(measured_lines)
percent = 100.0 if total == 0 else (covered * 100.0 / total)
print(f"{phase} service coverage: {covered}/{total} lines ({percent:.1f}%)")
if percent < 80.0:
    raise SystemExit(f"{phase} service coverage below 80%: {percent:.1f}%")
PY
}

uv run --no-sync --extra dev pytest -q "${selectors[@]}"
uv run --no-sync --extra dev ruff check "${sources[@]}"
uv run --no-sync --extra dev mypy "${sources[@]}"
uv run --no-sync --extra dev python "$cli" --help >/dev/null
coverage_gate
require_canonical_final_artifacts
final_mode_smoke
