"""Run a no-credential local/mock P6 agentic-loop demo transcript."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE = Path("evals/agentic/deploy_regression_payment_api.json")


def build_demo_transcript(fixture_path: Path = FIXTURE) -> list[str]:
    fixture: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
    actual = fixture["actual"]
    incident_id = f"demo-{fixture['scenario']}"
    return [
        "OpsCat P6 local/mock agentic loop demo",
        "Credentials: none (fixture-only, no external provider calls)",
        f"Incident: {incident_id}",
        f"1. observe: loaded fixture scenario {fixture['scenario']}",
        f"2. correlate: grouped signals as {actual['correlation_group']}",
        f"3. diagnose: top root cause is {actual['top_root_cause']}",
        f"4. plan: selected runbook {actual['runbook']}",
        f"5. risk: decision {actual['risk_decision']}",
        "6. act: mock remediation only; production mutations remain unavailable",
        f"7. verify: recovery state {actual['verification_result']}",
        "Operator URL: http://127.0.0.1:8000/operator/incidents/demo-deploy-regression",
        "Report artifact: /tmp/opscat-agentic-demo-report.md",
    ]


def main() -> None:
    print("\n".join(build_demo_transcript()))


if __name__ == "__main__":
    main()
