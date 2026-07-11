from __future__ import annotations

import ast
from pathlib import Path

from app.services.p109_release_evidence import AUTHORITY_SCANNED_MODULES, build_p109_authority_scan, zero_authority_counters

P109_AUTHORITY_SCANNED_MODULES = tuple(Path(path) for path in AUTHORITY_SCANNED_MODULES)

FORBIDDEN_IMPORT_PREFIXES = (
    "app.services.action_service",
    "app.services.execution_attempt_service",
    "app.models.action",
    "app.services.authorization",
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib.request",
    "boto3",
    "google.cloud",
    "kubernetes",
    "sqlalchemy",
    "psycopg",
    "sqlite3",
)

FORBIDDEN_CALLS = {
    "open",
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


def test_p109_authority_scan_modules_are_exact() -> None:
    assert {str(path) for path in P109_AUTHORITY_SCANNED_MODULES} == {
        "app/services/microremed_result_adapter.py",
        "app/services/p109_holdout_guard.py",
        "app/services/p109_safe_acquisition.py",
        "app/services/p109_source_manifest.py",
        "app/services/p109_release_evidence.py",
        "app/services/rcaeval_adapter.py",
        "app/services/rcaeval_diagnosis_benchmark.py",
        "app/services/remediation_outcome_benchmark_p109.py",
        "scripts/run_rcaeval_real_sample.py",
        "scripts/run_real_ops_benchmark.py",
    }
    assert all(path.exists() for path in P109_AUTHORITY_SCANNED_MODULES)


def test_p109_release_lane_has_no_online_database_or_execution_authority() -> None:
    for path in P109_AUTHORITY_SCANNED_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                assert not any(module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES), f"{path} imports forbidden authority module {module}"

            if isinstance(node, ast.Call):
                chain = _chain(node.func)
                assert chain not in FORBIDDEN_CALLS, f"{path} calls forbidden authority surface {chain}"


def test_p109_release_authority_counter_schema_is_exact_and_zero() -> None:
    assert zero_authority_counters() == EXPECTED_ZERO_COUNTERS


def test_p109_build_authority_scan_is_ast_derived_exact_and_fail_closed() -> None:
    scan = build_p109_authority_scan()

    assert scan["accepted"] is True
    assert tuple(scan["scanned_modules"]) == tuple(str(path) for path in P109_AUTHORITY_SCANNED_MODULES)
    assert scan["findings"] == []
    assert scan["authority_counters"] == EXPECTED_ZERO_COUNTERS
    assert scan["authority_scan_hash"].startswith("sha256:")
