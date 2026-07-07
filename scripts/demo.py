import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.main import app

    with TestClient(app) as client:
        health = client.get("/health")
        health.raise_for_status()
        incident_response = client.post(
            "/webhooks/alerts/mock?process_now=true",
            json={
                "scenario": "payment_api_deploy_regression",
                "environment": "staging",
                "severity": "high",
                "message": "Demo payment-api timeout spike",
            },
        )
        incident_response.raise_for_status()
        incident = incident_response.json()
        action = incident["actions"][0]
        approval_response = client.post(
            f"/approvals/{action['id']}",
            json={"decision": "approve", "actor": "demo-user", "reason": "README demo approval"},
        )
        approval_response.raise_for_status()
        approved = approval_response.json()
        night_response = client.post("/night-autopilot/simulate", json={})
        night_response.raise_for_status()
        print("Health:", health.json())
        print("Incident:", incident["id"], "initial_status=", incident["status"])
        print("Action:", action["action_type"], action["policy_decision"])
        print("Final status:", approved["incident"]["status"])
        print("Report path:", approved["report"])
        print("P8 flow: alert -> war room -> score -> runbook critique -> action gate -> report")
        print("P8 War Room URL:", f"/operator/incidents/{incident['id']}")
        print("P8 boundary: local/mock only; does not claim unattended production operation")
        print("Night Autopilot actions:", len(night_response.json()["actions_taken"]))
        print("Agentic loop demo:", "uv run --no-sync --extra dev python scripts/demo_agentic_loop.py")


if __name__ == "__main__":
    main()
