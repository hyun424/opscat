from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.p114_acceptance import (
    P114_RUNTIME_SAFETY_COUNTERS,
    P114AcceptanceError,
    P114RuntimeSafetyLedger,
)

AUTHORITATIVE_FILES = (
    Path("app/services/p114_acceptance.py"),
    Path("app/services/p114_fault_knn.py"),
    Path("app/services/p114_hypothesis_lattice.py"),
    Path("app/services/p114_re2_loader.py"),
    Path("scripts/freeze_p114_acceptance.py"),
    Path("scripts/run_p114_re2_ob_replay.py"),
    Path("scripts/run_p114_re2_ob_blind.py"),
)
FORBIDDEN_IMPORT_PREFIXES = (
    "app.services.action_service",
    "app.services.execution_attempt_service",
    "app.services.authorization",
    "openai",
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "boto3",
    "google.cloud",
    "kubernetes",
)
FORBIDDEN_CALLS = {
    "os.system",
    "os.popen",
    "subprocess.run",
    "subprocess.Popen",
    "socket.socket",
    "requests.get",
    "requests.post",
    "httpx.get",
    "httpx.post",
    "urllib.request.urlopen",
    "OpenAI",
    "ActionService.execute",
}


def test_authoritative_blind_path_has_no_llm_network_shell_or_remediation_surface() -> None:
    for path in AUTHORITATIVE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not _forbidden_import(alias.name), (path, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not _forbidden_import(node.module), (path, node.module)
            elif isinstance(node, ast.Call):
                chain = _attr_chain(node.func)
                assert chain not in FORBIDDEN_CALLS, (path, chain)


@pytest.mark.parametrize("counter", P114_RUNTIME_SAFETY_COUNTERS)
def test_runtime_safety_ledger_blocks_and_records_forbidden_capability(counter: str) -> None:
    ledger = P114RuntimeSafetyLedger()

    with pytest.raises(P114AcceptanceError, match="forbidden_runtime_capability"):
        ledger.record_forbidden(counter)

    assert ledger.snapshot()[counter] == 1
    assert sum(ledger.snapshot().values()) == 1


def _forbidden_import(module: str) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES)


def _attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attr_chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""
