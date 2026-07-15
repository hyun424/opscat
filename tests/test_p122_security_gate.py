from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_p122_security_gate.py"


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_p122_security_gate", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_lock(root: Path, package_name: str = "demo") -> None:
    root.joinpath("uv.lock").write_text(
        f"""
version = 1
revision = 3
requires-python = ">=3.12"

[[package]]
name = "{package_name}"
version = "1.2.3"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files.pythonhosted.org/packages/demo.tar.gz", hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", size = 1 }}
wheels = [
    {{ url = "https://files.pythonhosted.org/packages/demo.whl", hash = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", size = 1 }},
]
""".strip()
        + "\n"
    )


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)


def test_secret_scan_redacts_values_and_fails(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    secret = "ghp_" + "A" * 40
    tmp_path.joinpath("app.py").write_text(f'TOKEN = "{secret}"\n')
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")

    assert report["status"] == "fail"
    assert report["findings"][0]["rule_id"] == "secret.github_token"
    assert report["findings"][0]["fingerprint"]
    serialized = json.dumps(report)
    assert secret not in serialized


def test_sbom_uses_uv_lock_hashes_and_license_inventory(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path, package_name="demo-ok")
    gate.LICENSE_ALLOWLIST["demo-ok"] = "Apache-2.0"
    tmp_path.joinpath("app.py").write_text("VALUE = 1\n")
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")
    sbom = json.loads(tmp_path.joinpath("evals/p122/sbom.json").read_text())
    inventory = json.loads(tmp_path.joinpath("evals/p122/license-inventory.json").read_text())

    assert report["status"] == "pass"
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["components"][0]["hashes"][0]["alg"] == "SHA256"
    assert inventory["components"][0]["status"] == "allowed"


def test_unknown_or_incompatible_license_blocks_release(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path, package_name="demo-gpl")
    gate.LICENSE_ALLOWLIST["demo-gpl"] = "GPL-3.0-only"
    tmp_path.joinpath("app.py").write_text("VALUE = 1\n")
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")

    assert report["status"] == "fail"
    assert any(finding["rule_id"] == "license.incompatible" for finding in report["findings"])


def test_shell_subprocess_incident_action_blocks_release(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    tmp_path.joinpath("actions.py").write_text(
        """
import subprocess

def incident_action(command: str) -> None:
    subprocess.run(command, shell=True)
""".lstrip()
    )
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")

    assert report["status"] == "fail"
    assert any(finding["rule_id"] == "static.shell_subprocess_incident_action" for finding in report["findings"])


def test_arbitrary_subprocess_call_blocks_even_without_shell_or_incident_name(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    tmp_path.joinpath("runner.py").write_text(
        """
import subprocess

def run(command: str) -> None:
    subprocess.run(command)
""".lstrip()
    )
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")

    assert report["status"] == "fail"
    assert any(finding["rule_id"] == "static.arbitrary_subprocess_execution" for finding in report["findings"])


def test_p145_selector_runner_has_no_arbitrary_subprocess_surface() -> None:
    gate = load_gate()

    findings = gate.scan_shell_incident_paths(ROOT, [ROOT / "app/services/p145_runner.py"])

    assert not [finding for finding in findings if finding.rule_id == "static.arbitrary_subprocess_execution"]


def test_generated_archives_normalize_app_paths_before_subprocess_scan(tmp_path: Path) -> None:
    gate = load_gate()
    dist = tmp_path / "dist"
    dist.mkdir()
    payload = b"import subprocess\n\ndef run(command: str) -> None:\n    subprocess.run(command)\n"
    wheel = dist / "opscat-0.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("./app/unsafe_wheel.py", payload)
    sdist = dist / "opscat-0.2.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo("opscat-0.2.0/app/unsafe_sdist.py")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    findings = gate.scan_distribution_artifacts(tmp_path)

    arbitrary_paths = {finding.path for finding in findings if finding.rule_id == "static.arbitrary_subprocess_execution"}
    assert any("unsafe_wheel.py" in path for path in arbitrary_paths)
    assert any("unsafe_sdist.py" in path for path in arbitrary_paths)


def test_production_like_default_blocks_but_negated_docs_do_not(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    tmp_path.joinpath("settings.py").write_text(
        """
DEFAULT_ENDPOINT = "https://prod.example.com/api"
LIMITATION = "local demo, not production authentication"
""".lstrip()
    )
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")

    default_findings = [finding for finding in report["findings"] if finding["rule_id"] == "default.production_like_mutable_target"]
    assert report["status"] == "fail"
    assert len(default_findings) == 1
    assert default_findings[0]["line"] == 1


def test_security_report_binds_exact_source_and_archive_inventories(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    tmp_path.joinpath("app.py").write_text("VALUE = 1\n")
    dist = tmp_path / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / "opscat-0.2.0-py3-none-any.whl", "w") as archive:
        archive.writestr("app/__init__.py", "VALUE = 1\n")
    init_repo(tmp_path)

    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")

    assert report["schema_version"] == "p122.security_report.v2"
    assert report["scanned_file_count"] == len(report["source_inventory"])
    assert report["generated_artifact_scan_count"] == len(report["archive_inventory"])
    assert gate.security_report_current(report, root=tmp_path)

    tmp_path.joinpath("app.py").write_text("VALUE = 2\n")
    assert not gate.security_report_current(report, root=tmp_path)


def test_generated_release_evidence_does_not_invalidate_source_inventory(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    tmp_path.joinpath("app.py").write_text("VALUE = 1\n")
    init_repo(tmp_path)
    output_dir = tmp_path / "evals" / "p122"
    report = gate.build_security_report(tmp_path, output_dir)

    output_dir.joinpath("release-evidence.json").write_text('{"status":"blocked"}\n')

    assert gate.security_report_current(report, root=tmp_path)


def test_security_report_is_checkout_portable_but_stales_on_archive_backdoor(tmp_path: Path) -> None:
    gate = load_gate()
    write_lock(tmp_path)
    gate.LICENSE_ALLOWLIST["demo"] = "MIT"
    tmp_path.joinpath("app.py").write_text("VALUE = 1\n")
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "opscat-0.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("app/__init__.py", "VALUE = 1\n")
    init_repo(tmp_path)
    report = gate.build_security_report(tmp_path, tmp_path / "evals" / "p122")
    relocated = tmp_path.parent / f"{tmp_path.name}-relocated"
    shutil.copytree(tmp_path, relocated)

    assert report["root"] == "."
    assert gate.security_report_current(report, root=relocated)

    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("app/backdoor.py", "import subprocess\nsubprocess.run(input())\n")

    assert not gate.security_report_current(report, root=tmp_path)
