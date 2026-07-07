from __future__ import annotations

from pathlib import Path


def test_p7_release_evidence_lists_commands_and_local_mock_boundary() -> None:
    final = Path("docs/operations/p7-final-summary.md").read_text()
    release = Path("docs/release-evidence.md").read_text()
    roadmap = Path("ROADMAP.md").read_text()

    assert "bash scripts/verify.sh --profile full" in final
    assert "scripts/run_replay_evals.py" in final
    assert "local/mock reliability evidence" in final
    assert "P7" in release
    assert "P7" in roadmap
