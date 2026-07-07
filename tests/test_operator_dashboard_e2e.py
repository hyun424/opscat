"""Browser-contract tests for the server-rendered operator dashboard."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS


class DashboardHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.testids: list[str] = []
        self.hrefs: list[str] = []
        self.tags: list[str] = []
        self.text_parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(part.strip() for part in self.text_parts if part.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        attr_map = dict(attrs)
        if attr_map.get("data-testid"):
            self.testids.append(str(attr_map["data-testid"]))
        if tag == "a" and attr_map.get("href"):
            self.hrefs.append(str(attr_map["href"]))

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)


def parse_dashboard(html: str) -> DashboardHTML:
    parsed = DashboardHTML()
    parsed.feed(html)
    return parsed


def test_operator_dashboard_browser_contract_exposes_safe_navigation_and_report_link(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "browser-contract-nav", "scenario": "payment_bad_deploy", "message": "browser contract incident"},
    )
    assert created.status_code == 201
    incident = created.json()
    action = incident["actions"][0]
    decided = client.post(
        f"/approvals/{action['id']}",
        headers=ALPHA_HEADERS,
        json={"decision": "approve", "reason": "browser contract evidence"},
    )
    assert decided.status_code == 200

    inbox_response = client.get("/operator", headers=ALPHA_HEADERS)
    assert inbox_response.status_code == 200
    inbox = parse_dashboard(inbox_response.text)

    assert "operator-shell" in inbox.testids
    assert "incident-inbox" in inbox.testids
    assert "incident-table" in inbox.testids
    assert "incident-row" in inbox.testids
    assert f"/operator/incidents/{incident['id']}" in inbox.hrefs
    assert "browser contract incident" in inbox.text

    detail_response = client.get(f"/operator/incidents/{incident['id']}", headers=ALPHA_HEADERS)
    assert detail_response.status_code == 200
    detail = parse_dashboard(detail_response.text)

    for required_testid in {
        "operator-shell",
        "incident-detail",
        "evidence-list",
        "timeline-list",
        "action-card",
        "execution-attempt-list",
        "report-link",
    }:
        assert required_testid in detail.testids
    assert "/operator" in detail.hrefs
    assert f"/incidents/{incident['id']}/report" in detail.hrefs
    assert "Execution attempts" in detail.text
    assert "approval_granted" in detail.text or f"/approvals/{action['id']}" in detail.text
    assert "form" not in detail.tags, "dashboard must not add mutation forms before permission UX exists"


def test_operator_dashboard_browser_contract_escapes_untrusted_alert_text(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={
            "idempotency_key": "browser-contract-escape",
            "scenario": "payment_bad_deploy",
            "message": "<script>alert('ops')</script> & raw",
        },
    )
    assert created.status_code == 201

    page = client.get("/operator", headers=ALPHA_HEADERS)

    assert page.status_code == 200
    assert "<script>alert('ops')</script>" not in page.text
    assert "&lt;script&gt;alert(&#x27;ops&#x27;)&lt;/script&gt; &amp; raw" in page.text
    parsed = parse_dashboard(page.text)
    assert "<script>alert('ops')</script> & raw" in parsed.text
