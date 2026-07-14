from __future__ import annotations

import ast
from pathlib import Path

from app.services.p137_contracts import zero_forbidden_authority

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCES = tuple(sorted((ROOT / "app/services").glob("p137_*.py")))
BANNED_IMPORT_ROOTS = {
    "boto3",
    "botocore",
    "httpx",
    "kubernetes",
    "openai",
    "requests",
    "socket",
    "subprocess",
    "urllib",
}


def test_p137_runtime_sources_have_no_external_or_execution_imports() -> None:
    assert RUNTIME_SOURCES
    violations: list[str] = []
    for path in RUNTIME_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".", 1)[0] in BANNED_IMPORT_ROOTS:
                    violations.append(f"{path.name}:{node.lineno}:{name}")
    assert violations == []


def test_p137_runtime_sources_do_not_read_environment_or_launch_commands() -> None:
    violations: list[str] = []
    for path in RUNTIME_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if isinstance(owner, ast.Name) and owner.id == "os" and node.func.attr in {"getenv", "popen", "system"}:
                    violations.append(f"{path.name}:{node.lineno}:os.{node.func.attr}")
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                owner = node.value.value
                if isinstance(owner, ast.Name) and owner.id == "os" and node.value.attr == "environ":
                    violations.append(f"{path.name}:{node.lineno}:os.environ")
    assert violations == []


def test_p137_forbidden_authority_schema_is_complete_and_exact_zero() -> None:
    counters = zero_forbidden_authority()
    assert len(counters) == 15
    assert all(type(value) is int and value == 0 for value in counters.values())
