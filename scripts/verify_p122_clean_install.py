#!/usr/bin/env python3
"""Verify wheel install, local demo/contracts, and uninstall in a clean venv."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from packaging.markers import Marker, default_environment

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS  # noqa: E402

WHEEL = "opscat-0.2.0-py3-none-any.whl"


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_evidence(evidence: dict[str, Any], *, root: Path = ROOT) -> bool:
    wheel = root / "dist" / WHEEL
    audited_graph = audited_runtime_dependency_graph(root)
    return (
        evidence.get("schema_version") == "p122.clean_install.v1"
        and evidence.get("wheel_hash") == file_hash(wheel)
        and evidence.get("audited_lock_runtime_graph") == audited_graph
        and evidence.get("installed_runtime_graph") == audited_graph
        and evidence.get("install_exit_code") == 0
        and evidence.get("demo_exit_code") == 0
        and evidence.get("contracts_exit_code") == 0
        and evidence.get("uninstall_exit_code") == 0
        and evidence.get("import_residue_after_uninstall") is False
        and _exact_p121_authority_zero(evidence.get("authority_counters"))
        and evidence.get("exact_nonlocal_authority_zero") is True
    )


def verify_clean_install(*, root: Path) -> dict[str, Any]:
    wheel = root / "dist" / WHEEL
    with tempfile.TemporaryDirectory(prefix="opscat-p122-install-") as temp_dir:
        venv = Path(temp_dir) / "venv"
        requirements = Path(temp_dir) / "requirements.txt"
        subprocess.run(
            ["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--format", "requirements-txt", "--output-file", str(requirements)],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["uv", "venv", str(venv)], check=True, capture_output=True, text=True)
        python = venv / "bin" / "python"
        executable = venv / "bin" / "opscat"
        install = subprocess.run(["uv", "pip", "install", "--python", str(python), "--requirement", str(requirements), str(wheel)], capture_output=True, text=True)
        environment = {key: value for key, value in os.environ.items() if key not in {"NVIDIA_API_KEY", "OPENAI_API_KEY", "DATABASE_URL"}}
        environment["OPSCAT_MODE"] = "local"
        demo_artifact = Path(temp_dir) / "demo-replay.json"
        demo = subprocess.run([str(executable), "demo", "--output", str(demo_artifact)], capture_output=True, text=True, env=environment, cwd=temp_dir)
        contracts = subprocess.run([str(executable), "contracts"], capture_output=True, text=True, env=environment, cwd=temp_dir)
        installed_graph = json.loads(
            subprocess.run(
                [
                    str(python),
                    "-c",
                    (
                        "import importlib.metadata,json; "
                        "print(json.dumps(sorted({d.metadata['Name'].lower().replace('_','-') + '==' + d.version "
                        "for d in importlib.metadata.distributions() "
                        "if d.metadata['Name'].lower().replace('_','-') not in {'pip','setuptools','wheel'}})))"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        uninstall = subprocess.run(["uv", "pip", "uninstall", "--python", str(python), "opscat"], capture_output=True, text=True)
        residue = subprocess.run([str(python), "-c", "import importlib.util; raise SystemExit(importlib.util.find_spec('app') is not None)"], capture_output=True, text=True, cwd=temp_dir)
        demo_payload = json.loads(demo_artifact.read_text()) if demo.returncode == 0 and demo_artifact.is_file() else {}
    authority = demo_payload.get("authority_counters") if isinstance(demo_payload, dict) else None
    exact_zero = _exact_p121_authority_zero(authority)
    audited_graph = audited_runtime_dependency_graph(root)
    evidence: dict[str, Any] = {
        "schema_version": "p122.clean_install.v1",
        "wheel_hash": file_hash(wheel),
        "audited_lock_runtime_graph": audited_graph,
        "installed_runtime_graph": installed_graph,
        "install_exit_code": install.returncode,
        "demo_exit_code": demo.returncode,
        "contracts_exit_code": contracts.returncode,
        "uninstall_exit_code": uninstall.returncode,
        "import_residue_after_uninstall": residue.returncode != 0,
        "authority_counters": authority,
        "exact_nonlocal_authority_zero": exact_zero,
        "secrets_removed_from_environment": True,
        "scope": "clean temporary venv; fixture/local demo only",
    }
    evidence["report_hash"] = "sha256:" + hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output = root / "evals" / "p122" / "clean-install.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    if not validate_evidence(evidence, root=root):
        raise SystemExit(f"P122 clean install failed closed: {evidence!r}")
    return evidence


def _exact_p121_authority_zero(authority: Any) -> bool:
    return isinstance(authority, dict) and set(authority) == set(P121_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(authority.get(key), int) and not isinstance(authority.get(key), bool) and authority.get(key) == 0
        for key in P121_AUTHORITY_COUNTER_KEYS
    )


def audited_runtime_dependency_graph(root: Path) -> list[str]:
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = {str(package["name"]).lower().replace("_", "-"): package for package in lock.get("package", []) if isinstance(package, dict) and package.get("name") and package.get("version")}
    environment = default_environment()
    seen: dict[str, set[str]] = {}

    def visit(name: str, extras: tuple[str, ...] = ()) -> None:
        normalized = name.lower().replace("_", "-")
        was_seen = normalized in seen
        selected_extras = seen.setdefault(normalized, set())
        new_extras = set(extras) - selected_extras
        if was_seen and not new_extras:
            return
        selected_extras.update(extras)
        package = packages.get(normalized)
        if package is None:
            return
        for dependency in package.get("dependencies", []):
            if isinstance(dependency, dict) and dependency.get("name") and _marker_applies(dependency.get("marker"), environment):
                visit(str(dependency["name"]), _dependency_extras(dependency))
        optional = package.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for extra in sorted(extras):
                for dependency in optional.get(extra, []):
                    if isinstance(dependency, dict) and dependency.get("name") and _marker_applies(dependency.get("marker"), environment):
                        visit(str(dependency["name"]), _dependency_extras(dependency))

    visit("opscat")
    return sorted(f"{name}=={packages[name]['version']}" for name in seen if name in packages)


def _dependency_extras(dependency: dict[str, Any]) -> tuple[str, ...]:
    raw = dependency.get("extra", dependency.get("extras", ()))
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(str(item) for item in raw)
    return ()


def _marker_applies(marker: Any, environment: Mapping[str, Any]) -> bool:
    if not isinstance(marker, str) or not marker:
        return True
    return Marker(marker).evaluate(environment)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        evidence = json.loads((args.root / "evals" / "p122" / "clean-install.json").read_text())
        if not isinstance(evidence, dict) or not validate_evidence(evidence, root=args.root):
            raise SystemExit("P122 clean-install evidence is missing, stale, or invalid")
    else:
        evidence = verify_clean_install(root=args.root)
    print(json.dumps({"status": "pass", "wheel_hash": evidence.get("wheel_hash")}, sort_keys=True))


if __name__ == "__main__":
    main()
