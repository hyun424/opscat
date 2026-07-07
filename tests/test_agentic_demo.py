from __future__ import annotations

import subprocess
import sys


def test_agentic_demo_command_prints_seven_stages() -> None:
    result = subprocess.run([sys.executable, "scripts/demo_agentic_loop.py"], check=True, capture_output=True, text=True)

    for stage in ["observe", "correlate", "diagnose", "plan", "risk", "act", "verify"]:
        assert f"{stage}:" in result.stdout
    assert "no external credentials" in result.stdout
