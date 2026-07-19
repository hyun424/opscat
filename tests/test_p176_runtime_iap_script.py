from __future__ import annotations

import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_IAP = ROOT / "infra" / "gcp" / "p176-live" / "runtime-iap.sh"
RUNTIME_CLI = ROOT / "scripts" / "run_p176_live_runtime_bridge.py"


def test_runtime_iap_script_keeps_p176_live_iap_and_no_terraform_mutation_contracts() -> None:
    script = RUNTIME_IAP.read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script
    assert 'ALLOWED_ZONE="asia-northeast3-a"' in script
    assert 'TARGET_INSTANCE="p176-live-target"' in script
    assert 'OBSERVER_INSTANCE="p176-live-observer"' in script
    assert 'TARGET_PRIVATE_IP="10.176.0.10"' in script
    assert 'OBSERVER_PRIVATE_IP="10.176.0.20"' in script
    assert "EXPECTED_PROJECT_ID must be a dedicated opscat-p176-live-* project" in script
    assert "gcloud compute ssh" in script
    assert "--tunnel-through-iap" in script
    assert "gcloud compute start-iap-tunnel" not in script
    assert "terraform -chdir" not in script
    assert "terraform apply" not in script
    assert "terraform destroy" not in script
    assert "APPLY_REVIEWED" not in script
    assert "BEGIN PRIVATE KEY" not in script
    assert "NVIDIA_API_KEY" not in script
    assert "openssl rand -hex 32" in script
    assert "P176_FAULT_CAPABILITY_TOKEN" in script
    assert "runtime-capability.env" in script
    assert "cleanup_remote_capability" in script
    assert 'trap "${cleanup_cmd}" EXIT' in script
    assert "kill %q %q 2>/dev/null || true; wait %q %q 2>/dev/null || true" in script
    assert "REVIEWED_APPLY_PLAN_SHA256" in script
    assert "REVIEWED_TEARDOWN_PLAN_SHA256" in script
    assert "REVIEWED_COST_CUTOFF_APPLY_PLAN_SHA256" in script
    assert "REVIEWED_COST_CUTOFF_DESTROY_PLAN_SHA256" in script
    assert "RUNTIME_SOURCE_MANIFEST_SHA256" in script
    assert "runtime source manifest digest mismatch" in script
    assert "app/services/p176_live_runtime.py" in script
    assert "app/services/p176_runtime_bridge.py" in script
    assert "scripts/run_p176_live_runtime_bridge.py" in script
    assert 'chmod 0444 "${observer_staging}/telemetry_collector.py"' in script
    assert "sudo chmod 0755 /opt/opscat/p176-live/observer" in script
    assert "sudo chmod 0444 /opt/opscat/p176-live/observer/telemetry_collector.py" in script


def test_runtime_plan_is_digest_bound_and_rejects_wrong_project(tmp_path: Path) -> None:
    artifacts = _write_plan_artifacts(tmp_path)
    plan_dir = Path("/tmp") / f"opscat-p176-runtime-{tmp_path.name}"
    if plan_dir.exists():
        shutil.rmtree(plan_dir)
    env = _runtime_env(tmp_path, artifacts)
    env["P176_RUNTIME_PLAN_DIR"] = str(plan_dir)
    env["EXPECTED_PROJECT_ID"] = "shared-vpc"

    failed = subprocess.run([str(RUNTIME_IAP), "plan"], env=env, text=True, capture_output=True, check=False)

    assert failed.returncode == 1
    assert "dedicated opscat-p176-live" in failed.stderr
    assert not plan_dir.exists()

    env["EXPECTED_PROJECT_ID"] = "opscat-p176-live-test01"
    result = subprocess.run([str(RUNTIME_IAP), "plan"], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    plan_file = plan_dir / "p176-runtime-plan.env"
    plan_text = plan_file.read_text(encoding="utf-8")
    assert "PLAN_KIND=p176-runtime-entry" in plan_text
    assert "PROJECT_ID=opscat-p176-live-test01" in plan_text
    assert f"REVIEWED_APPLY_PLAN_ARTIFACT={artifacts['apply']}" in plan_text
    assert "REVIEWED_APPLY_PLAN_SHA256=" in plan_text
    assert "RUNTIME_SOURCE_MANIFEST_SHA256=" in plan_text
    assert (plan_dir / "p176-runtime-plan.env.sha256").is_file()


def test_runtime_run_uses_fake_iap_tunnels_and_invokes_bridge_without_real_gcp(tmp_path: Path) -> None:
    artifacts = _write_plan_artifacts(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.jsonl"
    _write_fake_gcloud(fake_bin / "gcloud", command_log)
    _write_fake_curl(fake_bin / "curl", command_log)
    _write_fake_python(fake_bin / "python3", command_log)

    plan_dir = Path("/tmp") / f"opscat-p176-runtime-run-{tmp_path.name}"
    if plan_dir.exists():
        shutil.rmtree(plan_dir)
    env = _runtime_env(tmp_path, artifacts)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["P176_RUNTIME_PLAN_DIR"] = str(plan_dir)
    plan = subprocess.run([str(RUNTIME_IAP), "plan"], env=env, text=True, capture_output=True, check=False)
    assert plan.returncode == 0, plan.stderr
    plan_file = plan_dir / "p176-runtime-plan.env"
    plan_sha = (plan_dir / "p176-runtime-plan.env.sha256").read_text(encoding="utf-8").split()[0]

    run_dir = tmp_path / "run"
    env["P176_RUNTIME_PLAN_FILE"] = str(plan_file)
    env["EXPECTED_P176_RUNTIME_PLAN_SHA256"] = plan_sha
    env["P176_RUNTIME_RUN_DIR"] = str(run_dir)
    env["PYTHON_BIN"] = "python3"
    result = subprocess.run([str(RUNTIME_IAP), "run"], env=env, text=True, capture_output=True, check=False, timeout=20)

    assert result.returncode == 0, result.stderr
    calls = [_parse_call(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
    gcloud_calls = [call for call in calls if call["tool"] == "gcloud"]
    tunnel_calls = [call for call in gcloud_calls if "-N" in call["args"]]
    deploy_calls = [call for call in gcloud_calls if "-N" not in call["args"]]
    assert len(tunnel_calls) == 2
    assert all("--tunnel-through-iap" in call["args"] for call in tunnel_calls)
    assert any("p176-live-target" in call["args"] for call in tunnel_calls)
    assert any("p176-live-observer" in call["args"] for call in tunnel_calls)
    assert sum("scp" in call["args"] for call in deploy_calls) == 3
    assert sum("ssh" in call["args"] for call in deploy_calls) >= 3
    assert any("docker compose" in " ".join(call["args"]) and "p176-live-target" in call["args"] for call in deploy_calls)
    assert any("docker compose" in " ".join(call["args"]) and "p176-live-observer" in call["args"] for call in deploy_calls)
    assert not any("terraform" in " ".join(call["args"]) for call in calls)
    python_calls = [
        call
        for call in calls
        if call["tool"] == "python" and any(str(arg).endswith("run_p176_live_runtime_bridge.py") for arg in call["args"])
    ]
    assert len(python_calls) == 1
    bridge_args = python_calls[0]["args"]
    assert "--target-endpoint" in bridge_args
    assert "--observer-endpoint" in bridge_args
    assert str(run_dir) in bridge_args
    expected_copies = {
        "--reviewed-apply-plan-artifact": ("reviewed-p176-live-apply.plan", artifacts["apply"]),
        "--reviewed-teardown-plan-artifact": ("reviewed-p176-live-destroy.plan", artifacts["teardown"]),
        "--reviewed-cost-cutoff-apply-plan-artifact": (
            "reviewed-p176-cost-cutoff-apply.plan",
            artifacts["cost_apply"],
        ),
        "--reviewed-cost-cutoff-destroy-plan-artifact": (
            "reviewed-p176-cost-cutoff-destroy.plan",
            artifacts["cost_destroy"],
        ),
    }
    for flag, (filename, source) in expected_copies.items():
        copied = run_dir / filename
        assert bridge_args[bridge_args.index(flag) + 1] == str(copied)
        assert copied.is_file()
        assert not copied.is_symlink()
        assert sha256(copied.read_bytes()).hexdigest() == sha256(source.read_bytes()).hexdigest()


def test_runtime_cli_requires_service_and_chains_existing_scripts(tmp_path: Path) -> None:
    bridge = RUNTIME_CLI.read_text(encoding="utf-8")

    assert "importlib.import_module(\"app.services.p176_runtime_bridge\")" in bridge
    assert "run_p176_live_bridge.py" in bridge
    assert "run_p176_live_qualification.py" in bridge
    assert "--reviewed-apply-plan-artifact" in bridge
    assert "--skip-runtime-service" not in bridge
    assert 'return {"status": "not_available"}' not in bridge


def test_actual_runtime_entrypoint_collects_without_finalizing(tmp_path: Path, monkeypatch: Any) -> None:
    from app.services import p176_runtime_bridge as service

    calls: list[str] = []

    class Producer:
        def collect(self, run_dir: Path) -> Path:
            calls.append("collect")
            (run_dir / service.COLLECTION_RECEIPT_PATH).write_text("{}\n", encoding="utf-8")
            return run_dir

        def finalize(self, run_dir: Path, *, now: object) -> Path:
            calls.append("finalize")
            return run_dir

    monkeypatch.setenv("P176_RUNTIME_PHASE", "collect")
    monkeypatch.setattr(service, "_build_runtime_producer", lambda **_kwargs: Producer())

    result = service.run_p176_runtime_bridge(
        run_dir=tmp_path / "run",
        target_endpoint="http://127.0.0.1:40100",
        observer_endpoint="http://127.0.0.1:40200",
    )

    assert result["status"] == "runtime_collection_complete"
    assert calls == ["collect"]
    assert not (tmp_path / "run" / service.FINALIZATION_RECEIPT_PATH).exists()


def test_actual_runtime_entrypoint_rejects_non_loopback_endpoint_before_provider_factory(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from app.services import p176_runtime_bridge as service

    def unexpected_factory(**_kwargs: object) -> object:
        raise AssertionError("provider factory must not run")

    monkeypatch.setattr(service, "_build_runtime_producer", unexpected_factory)

    with pytest.raises(service.P176RuntimeBridgeError, match="target_endpoint_not_allowed"):
        service.run_p176_runtime_bridge(
            run_dir=tmp_path / "run",
            target_endpoint="http://169.254.169.254:80",
            observer_endpoint="http://127.0.0.1:40200",
        )


def test_runtime_cli_stops_after_real_module_collection_without_qualification(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from app.services import p176_runtime_bridge as service
    from scripts import run_p176_live_runtime_bridge as cli

    calls: list[tuple[str, object]] = []

    class Producer:
        def collect(self, run_dir: Path) -> Path:
            calls.append(("collect", run_dir))
            (run_dir / service.COLLECTION_RECEIPT_PATH).write_text("{}\n", encoding="utf-8")
            return run_dir

        def finalize(self, run_dir: Path, *, now: object) -> Path:
            raise AssertionError("finalize must not run in collect phase")

    monkeypatch.setenv("P176_RUNTIME_PHASE", "collect")
    monkeypatch.setattr(service, "_build_runtime_producer", lambda **_kwargs: Producer())

    def fake_existing_script(script_name: str, args: list[str]) -> dict[str, object]:
        calls.append((script_name, list(args)))
        return {"status": "ok", "script": script_name}

    monkeypatch.setattr(cli, "_run_existing_script", fake_existing_script)

    result = cli.run_runtime_bridge(
        run_dir=tmp_path / "run",
        target_endpoint="http://127.0.0.1:40100",
        observer_endpoint="http://127.0.0.1:40200",
    )

    assert result["status"] == "runtime_collection_complete"
    assert calls == [("collect", tmp_path / "run")]


def test_runtime_cli_invokes_bridge_and_qualification_after_real_module_finalization(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from app.services import p176_runtime_bridge as service
    from scripts import run_p176_live_runtime_bridge as cli

    calls: list[tuple[str, object]] = []

    class Producer:
        def collect(self, run_dir: Path) -> Path:
            raise AssertionError("collect must not run in finalize phase")

        def finalize(self, run_dir: Path, *, now: object) -> Path:
            calls.append(("finalize", run_dir))
            (run_dir / service.FINALIZATION_RECEIPT_PATH).write_text("{}\n", encoding="utf-8")
            return run_dir

    monkeypatch.setenv("P176_RUNTIME_PHASE", "finalize")
    monkeypatch.setattr(service, "_build_runtime_producer", lambda **_kwargs: Producer())

    def fake_existing_script(script_name: str, args: list[str]) -> dict[str, object]:
        calls.append((script_name, list(args)))
        return {"status": "ok", "script": script_name}

    monkeypatch.setattr(cli, "_run_existing_script", fake_existing_script)

    result = cli.run_runtime_bridge(
        run_dir=tmp_path / "run",
        target_endpoint="http://127.0.0.1:40100",
        observer_endpoint="http://127.0.0.1:40200",
    )

    assert result["status"] == "runtime_bridge_complete"
    assert calls[0][0] == "finalize"
    assert calls[1][0] == "run_p176_live_bridge.py"
    assert calls[2][0] == "run_p176_live_qualification.py"


def test_runtime_cli_fails_closed_when_runtime_module_has_no_supported_entrypoint(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import types

    from scripts import run_p176_live_runtime_bridge as cli

    service = types.ModuleType("app.services.p176_runtime_bridge")
    monkeypatch.setitem(sys.modules, "app.services.p176_runtime_bridge", service)

    with pytest.raises(cli.P176RuntimeBridgeCliError, match="runtime service entrypoint is missing"):
        cli._invoke_runtime_service(
            run_dir=tmp_path / "run",
            target_endpoint="http://127.0.0.1:40100",
            observer_endpoint="http://127.0.0.1:40200",
        )


def test_runtime_cli_rejects_partial_runtime_service_signature(tmp_path: Path) -> None:
    from scripts import run_p176_live_runtime_bridge as cli

    def partial_service(*, run_dir: Path) -> dict[str, object]:
        return {"run_dir": run_dir}

    with pytest.raises(cli.P176RuntimeBridgeCliError, match="runtime service signature mismatch"):
        cli._call_service(
            partial_service,
            run_dir=tmp_path / "run",
            target_endpoint="http://127.0.0.1:40100",
            observer_endpoint="http://127.0.0.1:40200",
        )


def _runtime_env(tmp_path: Path, artifacts: dict[str, Path]) -> dict[str, str]:
    env = os.environ.copy()
    env["EXPECTED_PROJECT_ID"] = "opscat-p176-live-test01"
    env["REVIEWED_APPLY_PLAN_ARTIFACT"] = str(artifacts["apply"])
    env["REVIEWED_TEARDOWN_PLAN_ARTIFACT"] = str(artifacts["teardown"])
    env["REVIEWED_COST_CUTOFF_APPLY_PLAN_ARTIFACT"] = str(artifacts["cost_apply"])
    env["REVIEWED_COST_CUTOFF_DESTROY_PLAN_ARTIFACT"] = str(artifacts["cost_destroy"])
    return env


def _write_plan_artifacts(tmp_path: Path) -> dict[str, Path]:
    artifacts = {
        "apply": tmp_path / "p176-live.tfplan.json",
        "teardown": tmp_path / "p176-live-destroy.tfplan.json",
        "cost_apply": tmp_path / "p176-cost-cutoff.tfplan.json",
        "cost_destroy": tmp_path / "p176-cost-cutoff-destroy.tfplan.json",
    }
    for key, path in artifacts.items():
        path.write_text(f'{{"artifact":"{key}"}}\n', encoding="utf-8")
    return artifacts


def _write_fake_gcloud(path: Path, command_log: Path) -> None:
    _write_executable(
        path,
        f"""#!/usr/bin/env bash
set -euo pipefail
{_log_line("gcloud", command_log)}
if [[ " $* " == *" -N "* ]]; then
  while true; do sleep 1; done
fi
exit 0
""",
    )


def _write_fake_curl(path: Path, command_log: Path) -> None:
    _write_executable(
        path,
        f"""#!/usr/bin/env bash
set -euo pipefail
{_log_line("curl", command_log)}
exit 0
""",
    )


def _write_fake_python(path: Path, command_log: Path) -> None:
    _write_executable(
        path,
        f"""#!/usr/bin/env bash
set -euo pipefail
{_log_line("python", command_log)}
if [[ "${{1:-}}" == "-c" ]]; then
  echo "$(( 40000 + RANDOM % 1000 ))"
  exit 0
fi
echo '{{"phase":"p176","status":"runtime_bridge_complete"}}'
exit 0
""",
    )


def _log_line(tool: str, command_log: Path) -> str:
    return f"printf '%s\\t%s\\n' {tool!r} \"$*\" >> {str(command_log)!r}"


def _parse_call(line: str) -> dict[str, object]:
    tool, args = line.split("\t", 1)
    return {"tool": tool, "args": args.split()}


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
