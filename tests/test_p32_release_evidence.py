from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "Bearer secret-token")


def test_p32_ticket_roadmap_lists_replay_scope() -> None:
    text = Path("docs/operations/p32-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P32 Ticket Roadmap — Real Telemetry Replay Benchmark",
        "P32-001",
        "P32-002",
        "P32-003",
        "P32-004",
        "P32-005",
        "P32-006",
        "P32-007",
        "P32-008",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p32_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p32-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P32 Final Summary — Real Telemetry Replay Benchmark",
        "P32-001",
        "P32-002",
        "P32-003",
        "P32-004",
        "P32-005",
        "P32-006",
        "P32-007",
        "P32-008",
        "app/services/real_telemetry_replay_benchmark.py",
        "scripts/run_real_telemetry_replay_benchmark.py",
        "evals/telemetry/replay/p32_replay_pack.json",
        "real telemetry replay benchmark",
        "replay_score",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P32 Real Telemetry Replay Benchmark Evidence",
        "docs/operations/p32-ticket-roadmap.md",
        "docs/operations/p32-final-summary.md",
        "tests/test_real_telemetry_replay_benchmark.py",
        "tests/test_p32_release_evidence.py",
        "/tmp/opscat-real-telemetry-replay-latest.md",
    ]:
        assert required in release
    assert "P32 implemented as Real Telemetry Replay Benchmark evidence" in roadmap
    assert "real_telemetry_replay_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
