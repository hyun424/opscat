#!/usr/bin/env python3
"""Run the OpsCat local mock incident demo against a running API server.

The script intentionally uses only stdlib HTTP calls so it works without external
credentials or SDKs. Start the API first, then run:

    python3 scripts/demo_mock_incident.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ALERT: dict[str, Any] = {
    "scenario": "payment_bad_deploy",
    "source": "mock",
    "service": "payment-api",
    "environment": "production",
    "severity": "high",
    "title": "Payment API checkout timeout spike",
    "fingerprint": "payment-api:checkout-timeout:v42",
}


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - local/dev URL
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} failed: HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach OpsCat API at {base_url}: {exc}") from exc


def pick_action(analysis: dict[str, Any]) -> dict[str, Any] | None:
    action = analysis.get("recommended_action") or analysis.get("action")
    if isinstance(action, dict):
        return action
    actions = analysis.get("actions") or analysis.get("action_proposals") or []
    return actions[0] if actions else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat mock incident demo")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--approve", action="store_true", help="approve the first proposed action")
    args = parser.parse_args()

    print("1. Checking health")
    print(json.dumps(request_json(args.base_url, "GET", "/health"), indent=2))

    print("2. Creating mock payment_bad_deploy incident")
    incident = request_json(args.base_url, "POST", "/webhooks/alerts/mock?process_now=true", DEFAULT_ALERT)
    print(json.dumps(incident, indent=2))
    incident_id = incident.get("id") or incident.get("incident_id")
    if not incident_id:
        raise SystemExit("Mock alert response did not include an incident id")

    print("3. Running deterministic investigation")
    analysis = request_json(args.base_url, "POST", f"/incidents/{incident_id}/investigate")
    print(json.dumps(analysis, indent=2))

    action = pick_action(analysis)
    if args.approve and action:
        action_id = action.get("id") or action.get("action_id")
        if not action_id:
            raise SystemExit("Cannot approve action: investigation did not return an action id")
        print(f"4. Approving proposed action {action_id}")
        approval = request_json(
            args.base_url,
            "POST",
            f"/incidents/{incident_id}/actions/{action_id}/approve",
        )
        print(json.dumps(approval, indent=2))
    else:
        print("4. Approval skipped; rerun with --approve to execute the first approval-gated action")

    print("5. Verifying recovery")
    verification = request_json(args.base_url, "POST", f"/incidents/{incident_id}/verify")
    print(json.dumps(verification, indent=2))

    print("6. Fetching final report")
    report = request_json(args.base_url, "GET", f"/incidents/{incident_id}/report")
    print(json.dumps(report, indent=2))
    time.sleep(0.1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
