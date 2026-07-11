from __future__ import annotations

from pathlib import Path


def test_ci_runs_full_release_sequence_on_supported_os_python_matrix() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release_job = workflow.split("release-sequence:", 1)[1].split("container-package-config:", 1)[0]
    assert "os: [ubuntu-latest, macos-latest]" in release_job
    assert "python-version: ['3.12', '3.13', '3.14']" in release_job
    assert "for phase in 115 116 117 118 119 120 121 122" in release_job
    assert release_job.index("scripts/run_p122_security_gate.py") < release_job.index("for phase in 115 116 117 118 119 120 121 122")
    assert release_job.index("scripts/run_p122_vulnerability_audit.py") < release_job.index("for phase in 115 116 117 118 119 120 121 122")
    assert release_job.index("scripts/build_p122_release_evidence.py") < release_job.index("for phase in 115 116 117 118 119 120 121 122")
    assert "setup-uv" in release_job and "enable-cache: true" in release_job
    assert "upload-artifact" in release_job


def test_ci_container_job_validates_package_and_local_config_without_credentials() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    container_job = workflow.split("container-package-config:", 1)[1]
    assert "docker build" in container_job
    assert "docker compose config" in container_job
    assert "config/opscat.local.example.json" in container_job
    assert "production_mutation_enabled" in container_job
    assert "secrets:" not in container_job
