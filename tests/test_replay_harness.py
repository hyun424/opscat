from __future__ import annotations

from pathlib import Path

from app.services.replay_service import ReplayService


def test_replay_harness_loads_30_local_mock_scenarios() -> None:
    scenarios = ReplayService(Path("evals/replay")).load_scenarios()

    assert len(scenarios) >= 30
    assert all(s.input_alert.get("source", "mock") == "mock" for s in scenarios)
    assert all(not s.requires_external_credentials for s in scenarios)


def test_replay_runner_returns_structured_pass_fail_metrics(tmp_path: Path) -> None:
    service = ReplayService(Path("evals/replay"))
    report = service.run(output_json=tmp_path / "replay.json", output_md=tmp_path / "replay.md")

    assert report["total"] >= 30
    assert report["passed"] + report["failed"] == report["total"]
    assert {"scenario", "passed", "evidence"}.issubset(report["results"][0])
    assert (tmp_path / "replay.json").exists()
    assert "OpsCat P7 Replay Eval Report" in (tmp_path / "replay.md").read_text()
