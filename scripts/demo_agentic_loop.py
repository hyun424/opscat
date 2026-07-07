"""One-command local P6 agentic loop demo."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.main import app

    with TestClient(app) as client:
        created = client.post(
            "/webhooks/alerts/mock?process_now=true",
            json={
                "scenario": "payment_api_deploy_regression",
                "environment": "staging",
                "severity": "high",
                "message": "P6 demo payment-api timeout spike after deploy v1.42.0",
                "idempotency_key": "p6-demo-agentic-loop",
            },
        )
        created.raise_for_status()
        incident = created.json()
        action = incident["actions"][0]
        approved = client.post(
            f"/approvals/{action['id']}",
            json={"decision": "approve", "actor": "demo-user", "reason": "P6 local demo approval"},
        )
        approved.raise_for_status()
        final_incident = approved.json()["incident"]
        trace = client.get(f"/incidents/{incident['id']}/decision-trace")
        trace.raise_for_status()
        trace_entries = trace.json()["decision_trace"]
        print("OpsCat P6 agentic loop demo (local/mock; no external credentials)")
        print("Incident ID:", incident["id"])
        print("observe: fixture alert accepted")
        print("correlate:", incident["alert_fingerprint"])
        print("diagnose:", final_incident["root_cause_candidate"], "confidence=", final_incident["confidence"])
        print("plan: local deploy-regression runbook / rollback draft")
        print("risk:", action["policy_decision"], "risk=", action["risk_level"])
        print("act:", action["action_type"], "approved locally")
        print("verify:", final_incident["status"])
        print("report:", approved.json()["report"])
        print("operator URL:", f"/operator/incidents/{incident['id']}")
        print("trace entries:", len(trace_entries))


if __name__ == "__main__":
    main()
