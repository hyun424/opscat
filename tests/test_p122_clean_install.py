from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from app.services.p121_signals import zero_authority_counters
from scripts.verify_p122_clean_install import WHEEL, audited_runtime_dependency_graph, file_hash, validate_evidence


def valid_evidence(root: Path) -> dict[str, Any]:
    graph = audited_runtime_dependency_graph(root)
    return {
        "schema_version": "p122.clean_install.v1",
        "wheel_hash": file_hash(root / "dist" / WHEEL),
        "audited_lock_runtime_graph": graph,
        "installed_runtime_graph": graph,
        "install_exit_code": 0,
        "demo_exit_code": 0,
        "contracts_exit_code": 0,
        "uninstall_exit_code": 0,
        "import_residue_after_uninstall": False,
        "authority_counters": zero_authority_counters(),
        "exact_nonlocal_authority_zero": True,
    }


def test_clean_install_evidence_is_wheel_bound(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    tmp_path.joinpath("uv.lock").write_text(Path("uv.lock").read_text(encoding="utf-8"), encoding="utf-8")
    wheel = dist / WHEEL
    wheel.write_bytes(b"wheel")
    evidence = valid_evidence(tmp_path)
    assert validate_evidence(evidence, root=tmp_path)
    wheel.write_bytes(b"changed")
    assert not validate_evidence(evidence, root=tmp_path)


def test_clean_install_evidence_rejects_dependency_graph_drift(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    tmp_path.joinpath("uv.lock").write_text(Path("uv.lock").read_text(encoding="utf-8"), encoding="utf-8")
    wheel = dist / WHEEL
    wheel.write_bytes(b"wheel")
    evidence = valid_evidence(tmp_path)
    evidence["installed_runtime_graph"] = [*evidence["installed_runtime_graph"], "unexpected==1.0"]
    assert not validate_evidence(evidence, root=tmp_path)


@pytest.mark.parametrize("mutation", ["missing", "extra", "boolean", "nonzero"])
def test_clean_install_evidence_requires_exact_integer_zero_authority_mapping(tmp_path: Path, mutation: str) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    tmp_path.joinpath("uv.lock").write_text(Path("uv.lock").read_text(encoding="utf-8"), encoding="utf-8")
    dist.joinpath(WHEEL).write_bytes(b"wheel")
    evidence = valid_evidence(tmp_path)
    tampered = copy.deepcopy(evidence)
    counters = tampered["authority_counters"]
    assert isinstance(counters, dict)
    key = next(iter(zero_authority_counters()))
    if mutation == "missing":
        counters.pop(key)
    elif mutation == "extra":
        counters["unexpected_zero"] = 0
    elif mutation == "boolean":
        counters[key] = False
    else:
        counters[key] = 1

    assert not validate_evidence(tampered, root=tmp_path)
