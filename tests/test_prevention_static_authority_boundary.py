from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

P107_SOURCE_FILES = [
    Path("app/services/prevention_p106_handoff.py"),
    Path("app/services/prevention_cohort_fingerprints.py"),
    Path("app/services/prevention_policy_preflight.py"),
    Path("app/services/prevention_state_machine.py"),
    Path("app/services/prevention_episode_audit.py"),
    Path("app/services/prevention_canary_executor.py"),
    Path("app/services/prevention_canary_harness.py"),
    Path("app/services/prevention_durable_idempotency.py"),
    Path("app/services/prevention_canary_fixture_matrix.py"),
    Path("app/services/prevention_authority_sentinel.py"),
    Path("app/services/prevention_outcome_report.py"),
    Path("app/services/prevention_replay_gate.py"),
    Path("app/services/p107_release_evidence.py"),
    Path("scripts/run_prevention_canary_evidence.py"),
]

FORBIDDEN_IMPORT_PREFIXES = {
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
    "sqlalchemy.orm",
}

FORBIDDEN_REFERENCES = {
    "ActionExecutionAttempt",
    "ActionService.execute",
    "subprocess.run",
    "subprocess.Popen",
    "os.system",
    "os.popen",
    "socket.socket",
    "requests.get",
    "requests.post",
    "httpx.get",
    "httpx.post",
    "urllib.request.urlopen",
    "Session.commit",
    "session.commit",
    "db.session.commit",
    "os.getenv",
    "os.environ",
}

ZERO_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "production_adapter_calls": 0,
    "production_mutation": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "cloud_calls": 0,
    "db_mutation": 0,
}


def _attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attr_chain(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _attr_chain(node.func)
    if isinstance(node, ast.Subscript):
        return _attr_chain(node.value)
    return ""


def _api(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing {module_name} ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def test_ast_import_call_boundary_rejects_forbidden_references() -> None:
    present = [path for path in P107_SOURCE_FILES if path.exists()]
    missing = [str(path) for path in P107_SOURCE_FILES if not path.exists()]
    assert not missing, f"P107 RED: missing P107-owned source files for static boundary scan: {missing}"
    assert present

    for path in present:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(alias.name == prefix or alias.name.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES), f"{path} imports forbidden module {alias.name}"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module == prefix or node.module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES), f"{path} imports from forbidden module {node.module}"
                imported = {alias.name for alias in node.names}
                assert "ActionExecutionAttempt" not in imported
            if isinstance(node, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)):
                chain = _attr_chain(node.func if isinstance(node, ast.Call) else node)
                assert chain not in FORBIDDEN_REFERENCES, f"{path} references forbidden authority surface {chain}"


def test_static_boundary_scan_includes_all_p107_services_and_canary_cli() -> None:
    expected = {
        "app/services/prevention_p106_handoff.py",
        "app/services/prevention_cohort_fingerprints.py",
        "app/services/prevention_policy_preflight.py",
        "app/services/prevention_state_machine.py",
        "app/services/prevention_episode_audit.py",
        "app/services/prevention_canary_harness.py",
        "app/services/prevention_canary_executor.py",
        "app/services/prevention_durable_idempotency.py",
        "app/services/prevention_canary_fixture_matrix.py",
        "app/services/prevention_authority_sentinel.py",
        "app/services/prevention_outcome_report.py",
        "app/services/prevention_replay_gate.py",
        "app/services/p107_release_evidence.py",
        "scripts/run_prevention_canary_evidence.py",
    }

    assert {str(path) for path in P107_SOURCE_FILES} == expected


@pytest.mark.parametrize(
    "method_name",
    [
        "record_auth_attempt",
        "record_credential_read",
        "record_production_adapter_call",
        "record_production_mutation",
        "record_shell_call",
        "record_network_call",
        "record_cloud_mutation",
        "record_db_mutation",
    ],
)
def test_runtime_sentinel_blocks_forbidden_authority(method_name: str) -> None:
    api = _api("app.services.prevention_authority_sentinel")
    cls = getattr(api, "PreventionAuthoritySentinel", None)
    blocked_exc = getattr(api, "ForbiddenPreventionAuthority", RuntimeError)
    if cls is None:
        pytest.fail("P107 RED: expose PreventionAuthoritySentinel.", pytrace=False)

    sentinel = cls()
    method = getattr(sentinel, method_name, None)
    if method is None:
        pytest.fail(f"P107 RED: sentinel must expose {method_name}.", pytrace=False)

    with pytest.raises(blocked_exc):
        method("test sentinel breach")

    assert _get(sentinel, "blocked") is True
    assert sum(_get(sentinel, "counters", {}).values()) == 1


def test_release_evidence_contains_static_and_runtime_boundary_results() -> None:
    api = _api("app.services.prevention_outcome_report")
    builder = getattr(api, "build_prevention_release_evidence", None)
    if builder is None:
        pytest.fail("P107 RED: expose build_prevention_release_evidence(audit_records).", pytrace=False)

    evidence = builder(
        [
            {
                "event_type": "authority_boundary",
                "static_authority_boundary_passed": True,
                "runtime_authority_sentinel_passed": True,
                "authority_counters": dict(ZERO_COUNTERS),
            }
        ]
    )

    assert _get(evidence, "static_authority_boundary_passed") is True
    assert _get(evidence, "runtime_authority_sentinel_passed") is True
    assert _get(evidence, "authority_counters") == ZERO_COUNTERS
