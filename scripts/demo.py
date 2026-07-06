from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        health.raise_for_status()
        incident_response = client.post(
            "/webhooks/alerts/mock",
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
        print("Night Autopilot actions:", len(night_response.json()["actions_taken"]))


if __name__ == "__main__":
    main()
