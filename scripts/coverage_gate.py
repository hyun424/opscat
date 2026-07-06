#!/usr/bin/env python3
"""Stdlib-only coverage gate for OpsCat's local MVP.

This intentionally avoids adding coverage.py/pytest-cov until the project is ready
for a richer CI dependency set. It measures statement-line execution in app/ while
running pytest and fails if total coverage is below the configured threshold.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
import trace
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIN_TOTAL = 60.0


@dataclass(frozen=True)
class FileCoverage:
    path: str
    covered: int
    executable: int
    percent: float
    missing: list[int]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pytest under a stdlib trace coverage gate")
    parser.add_argument("--min-total", type=float, default=_configured_min_total(), help="minimum total app/ line coverage percentage")
    parser.add_argument("--json-output", default=None, help="optional path to write a JSON coverage summary")
    parser.add_argument("pytest_args", nargs="*", help="optional pytest args; defaults to -q")
    args = parser.parse_args()

    _prepare_test_environment()
    pytest_args = args.pytest_args or ["-q"]
    result = _run_pytest_under_trace(pytest_args)
    if result.exit_code != 0:
        return result.exit_code

    files = _calculate_file_coverage(result.covered_lines)
    total_covered = sum(item.covered for item in files)
    total_executable = sum(item.executable for item in files)
    total_percent = _percent(total_covered, total_executable)

    _print_report(files, total_covered, total_executable, total_percent, args.min_total)

    summary: dict[str, Any] = {
        "total": {
            "covered": total_covered,
            "executable": total_executable,
            "percent": total_percent,
            "min_total": args.min_total,
        },
        "files": [asdict(item) for item in files],
    }
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if total_percent < args.min_total:
        print(f"Coverage gate failed: {total_percent:.2f}% < {args.min_total:.2f}%", file=sys.stderr)
        return 1
    print(f"Coverage gate passed: {total_percent:.2f}% >= {args.min_total:.2f}%")
    return 0


def _configured_min_total() -> float:
    try:
        import tomllib

        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        value = data.get("tool", {}).get("opscat", {}).get("coverage", {}).get("min_total", DEFAULT_MIN_TOTAL)
        return float(value)
    except Exception:
        return DEFAULT_MIN_TOTAL


@dataclass(frozen=True)
class TraceRunResult:
    exit_code: int
    covered_lines: dict[Path, set[int]]


def _prepare_test_environment() -> None:
    tmpdir = tempfile.mkdtemp(prefix="opscat-coverage-")
    os.environ.setdefault("OPSCAT_MODE", "test")
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmpdir}/opscat-coverage.db")
    os.environ.setdefault("REPORT_DIR", f"{tmpdir}/reports")
    os.environ.pop("SENTRY_AUTH_TOKEN", None)
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("SLACK_BOT_TOKEN", None)


def _run_pytest_under_trace(pytest_args: list[str]) -> TraceRunResult:
    import pytest

    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.base_prefix, str(ROOT / ".venv")])
    exit_code = int(tracer.runfunc(pytest.main, pytest_args))
    covered_lines: dict[Path, set[int]] = {}
    for (filename, lineno), count in tracer.results().counts.items():
        if count <= 0:
            continue
        path = Path(filename).resolve()
        if _is_app_file(path):
            covered_lines.setdefault(path, set()).add(lineno)
    return TraceRunResult(exit_code=exit_code, covered_lines=covered_lines)


def _calculate_file_coverage(covered_lines: dict[Path, set[int]]) -> list[FileCoverage]:
    files: list[FileCoverage] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        executable = _executable_lines(path)
        if not executable:
            continue
        covered = covered_lines.get(path.resolve(), set()) & executable
        missing = sorted(executable - covered)
        rel = path.relative_to(ROOT).as_posix()
        files.append(
            FileCoverage(
                path=rel,
                covered=len(covered),
                executable=len(executable),
                percent=_percent(len(covered), len(executable)),
                missing=missing[:25],
            )
        )
    return files


def _is_app_file(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    return rel.parts[:1] == ("app",) and path.suffix == ".py"


def _executable_lines(path: Path) -> set[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    ignored = _docstring_lines(tree)
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            for lineno in range(getattr(node, "lineno", 0), getattr(node, "end_lineno", getattr(node, "lineno", 0)) + 1):
                if lineno > 0:
                    lines.add(lineno)
    return {line for line in lines if line not in ignored and not _line_excluded(path, line)}


def _docstring_lines(tree: ast.AST) -> set[int]:
    ignored: set[int] = set()
    candidates: list[list[ast.stmt]] = []
    if isinstance(tree, ast.Module):
        candidates.append(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            candidates.append(node.body)
    for body in candidates:
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            for lineno in range(body[0].lineno, getattr(body[0], "end_lineno", body[0].lineno) + 1):
                ignored.add(lineno)
    return ignored


def _line_excluded(path: Path, line: int) -> bool:
    text = path.read_text(encoding="utf-8").splitlines()
    if line - 1 >= len(text):
        return True
    content = text[line - 1].strip()
    return not content or content.startswith("#") or "pragma: no cover" in content


def _percent(covered: int, executable: int) -> float:
    if executable == 0:
        return 100.0
    return round((covered / executable) * 100, 2)


def _print_report(files: list[FileCoverage], covered: int, executable: int, percent: float, minimum: float) -> None:
    print("\nCoverage gate report")
    print("file                                             covered/executable   percent")
    print("-" * 78)
    for item in files:
        print(f"{item.path:<48} {item.covered:>4}/{item.executable:<4} {item.percent:>7.2f}%")
    print("-" * 78)
    print(f"TOTAL                                            {covered:>4}/{executable:<4} {percent:>7.2f}%  min={minimum:.2f}%")


if __name__ == "__main__":
    raise SystemExit(main())
