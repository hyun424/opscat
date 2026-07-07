"""Approval console contract for auth-deferred local operator UI."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS, BETA_HEADERS


class ConsoleHTML(HTMLParser):
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


def parse_html(html: str) -> ConsoleHTML:
    parsed = ConsoleHTML()
    parsed.feed(html)
    return parsed


def _create_pending_action(client: Any, *, headers: dict[str, str], key: str, message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=headers,
        json={"idempotency_key": key, "scenario": "payment_bad_deploy", "message": message},
    )
    assert response.status_code == 201
    incident = response.json()
    return incident, incident["actions"][0]


def test_operator_inbox_lists_pending_approvals_with_safe_action_links(client: Any) -> None:
    alpha_incident, alpha_action = _create_pending_action(client, headers=ALPHA_HEADERS, key="approval-console-alpha", message="alpha approval needed")
    beta_incident, beta_action = _create_pending_action(client, headers=BETA_HEADERS, key="approval-console-beta", message="beta approval hidden")

    page = client.get("/operator", headers=ALPHA_HEADERS)

    assert page.status_code == 200
    parsed = parse_html(page.text)
    assert "pending-approvals" in parsed.testids
    assert "pending-approval-row" in parsed.testids
    assert f"/operator/actions/{alpha_action['id']}" in parsed.hrefs
    assert alpha_action["id"] in parsed.text
    assert alpha_incident["id"] in parsed.text
    assert "REQUIRE_APPROVAL" in parsed.text
    assert "alpha approval needed" in parsed.text
    assert beta_action["id"] not in parsed.text
    assert beta_incident["id"] not in parsed.text
    assert "form" not in parsed.tags


def test_operator_action_detail_renders_preview_risk_evidence_and_api_instructions(client: Any) -> None:
    incident, action = _create_pending_action(client, headers=ALPHA_HEADERS, key="approval-console-detail", message="detail approval needed")

    page = client.get(f"/operator/actions/{action['id']}", headers=ALPHA_HEADERS)

    assert page.status_code == 200
    parsed = parse_html(page.text)
    for required_testid in {
        "action-detail",
        "action-preview",
        "action-risk",
        "action-preconditions",
        "action-post-checks",
        "action-evidence-ids",
        "action-approval-api",
    }:
        assert required_testid in parsed.testids
    assert f"/operator/incidents/{incident['id']}" in parsed.hrefs
    assert action["action_type"] in parsed.text
    assert action["target"] in parsed.text
    assert action["risk_level"] in parsed.text
    assert action["policy_decision"] in parsed.text
    assert "dry-run" in parsed.text.lower() or "payload" in parsed.text.lower()
    assert "POST /approvals/" in parsed.text
    assert "decision=approve" in parsed.text
    assert "decision=reject" in parsed.text
    for evidence_id in action["evidence_ids"]:
        assert evidence_id in parsed.text
    for precondition in action["preconditions"]:
        assert precondition in parsed.text
    for post_check in action["post_checks"]:
        assert post_check in parsed.text
    assert "form" not in parsed.tags


def test_operator_action_detail_respects_workspace_scope(client: Any) -> None:
    _incident, action = _create_pending_action(client, headers=ALPHA_HEADERS, key="approval-console-scope", message="scope approval needed")

    hidden = client.get(f"/operator/actions/{action['id']}", headers=BETA_HEADERS)

    assert hidden.status_code == 404
