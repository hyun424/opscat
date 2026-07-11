from __future__ import annotations

import ast
from pathlib import Path

P108_RUNTIME_FILES = (
    Path("app/services/prevention_p108_ingress.py"),
    Path("app/services/prevention_outcome_ledger.py"),
    Path("app/services/prevention_counterfactual.py"),
    Path("app/services/prevention_outcome_learner.py"),
    Path("app/services/prevention_learning_recommendations.py"),
    Path("app/services/prevention_learning_promotion.py"),
    Path("app/services/p108_release_evidence.py"),
)

FORBIDDEN_IMPORT_PREFIXES = (
    "app.services.action_service",
    "app.services.execution_attempt_service",
    "app.models.action",
    "app.services.authorization",
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "boto3",
    "google.cloud",
    "kubernetes",
    "sqlalchemy",
    "psycopg",
    "sqlite3",
)

FORBIDDEN_CALLS = {
    "open",
    "Path.write_text",
    "Path.write_bytes",
    "os.getenv",
    "os.putenv",
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
    "Session",
    "session.execute",
    "session.commit",
    "engine.connect",
    "engine.execute",
    "ActionService.execute",
}

EXPECTED_ZERO_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "subprocess_calls": 0,
    "cloud_calls": 0,
    "db_access": 0,
    "production_adapter_calls": 0,
    "production_mutation": 0,
    "live_calls": 0,
    "executor_calls": 0,
    "online_policy_writes": 0,
}


def _chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _chain(node.func)
    return ""


def test_p108_runtime_has_no_online_or_database_authority() -> None:
    missing = [str(path) for path in P108_RUNTIME_FILES if not path.exists()]
    assert not missing, f"P108 runtime files missing from authority scan: {missing}"

    for path in P108_RUNTIME_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                assert not any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ), f"{path} imports forbidden authority module {module}"

            if isinstance(node, ast.Call):
                chain = _chain(node.func)
                assert chain not in FORBIDDEN_CALLS, f"{path} calls forbidden authority surface {chain}"
                assert not chain.endswith((".write_text", ".write_bytes")), f"{path} mutates a file via {chain}"


def test_p108_runtime_scan_is_exact_and_cannot_silently_drop_modules() -> None:
    assert {str(path) for path in P108_RUNTIME_FILES} == {
        "app/services/prevention_p108_ingress.py",
        "app/services/prevention_outcome_ledger.py",
        "app/services/prevention_counterfactual.py",
        "app/services/prevention_outcome_learner.py",
        "app/services/prevention_learning_recommendations.py",
        "app/services/prevention_learning_promotion.py",
        "app/services/p108_release_evidence.py",
    }


def test_p108_release_authority_counter_schema_is_exact_and_zero() -> None:
    from app.services.p108_release_evidence import zero_authority_counters

    assert zero_authority_counters() == EXPECTED_ZERO_COUNTERS
