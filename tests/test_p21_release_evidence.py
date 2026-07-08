from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p21_ticket_roadmap_lists_runtime_scope() -> None:
    text = Path("docs/operations/p21-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P21 Ticket Roadmap — Runtime Loop Runner and Operator Control Plane",
        "P21-001",
        "P21-002",
        "P21-003",
        "P21-004",
        "P21-005",
        "P21-006",
        "P21-007",
        "P21-008",
        "No auth work",
        "No production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p21_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p21-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P21 Final Summary — Runtime Loop Runner and Operator Control Plane",
        "P21-001",
        "P21-002",
        "P21-003",
        "P21-004",
        "P21-005",
        "P21-006",
        "P21-007",
        "P21-008",
        "app/services/runtime_loop_control.py",
        "scripts/run_runtime_loop.py",
        "tests/test_runtime_loop_control_plane.py",
        "approval profile",
        "pause/resume/abort",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P21 Runtime Loop Runner and Operator Control Plane Evidence",
        "docs/operations/p21-ticket-roadmap.md",
        "docs/operations/p21-final-summary.md",
        "tests/test_runtime_loop_control_plane.py",
        "tests/test_p21_release_evidence.py",
        "/tmp/opscat-runtime-loop-latest.md",
    ]:
        assert required in release
    assert "P21 implemented as Runtime Loop Runner and Operator Control Plane evidence" in roadmap
    assert "runtime_loop_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
