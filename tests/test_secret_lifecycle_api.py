"""Local secret lifecycle API gates for P5."""

from __future__ import annotations

import json
from typing import Any

from app.models import AuditEvent, SecretRecord
from tests.test_operator_dashboard import ALPHA_HEADERS

VIEWER_HEADERS = ALPHA_HEADERS | {"X-OpsCat-Actor": "viewer@example.com", "X-OpsCat-Role": "viewer"}
SECRET_MARKERS = ("sntrys_secret_value", "ghp_secret_value", "xoxb-secret", "ops@example.com")


def test_secret_lifecycle_api_returns_metadata_only_and_audits(client: Any, db_session: Any) -> None:
    created = client.put(
        "/secrets/sentry.token",
        headers=ALPHA_HEADERS,
        json={"value": "sntrys_secret_value", "metadata": {"connector": "sentry.readonly", "owner_email": "ops@example.com"}},
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload == {
        "secret": {
            "tenant_id": "tenant-a",
            "workspace_id": "alpha",
            "name": "sentry.token",
            "provider": "local-envelope",
            "metadata": {"connector": "sentry.readonly", "owner_email": "[REDACTED]"},
        }
    }

    listed = client.get("/secrets", headers=ALPHA_HEADERS)
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload["secrets"] == [payload["secret"]]
    rendered = json.dumps(listed_payload, sort_keys=True)
    assert all(marker not in rendered for marker in SECRET_MARKERS)

    stored = db_session.query(SecretRecord).one()
    assert stored.ciphertext != "sntrys_secret_value"
    audit_types = [event.event_type for event in db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()]
    assert "secret_stored" in audit_types
    assert "secret_listed" in audit_types
    audit_blob = json.dumps([event.event_metadata for event in db_session.query(AuditEvent).all()], sort_keys=True)
    assert all(marker not in audit_blob for marker in SECRET_MARKERS)


def test_secret_lifecycle_api_update_delete_and_role_scope(client: Any, db_session: Any) -> None:
    viewer_put = client.put("/secrets/github.token", headers=VIEWER_HEADERS, json={"value": "ghp_secret_value"})
    assert viewer_put.status_code == 403

    created = client.put("/secrets/github.token", headers=ALPHA_HEADERS, json={"value": "ghp_secret_value", "metadata": {"connector": "github.issues"}})
    assert created.status_code == 200
    updated = client.put("/secrets/github.token", headers=ALPHA_HEADERS, json={"value": "ghp_rotated_value", "metadata": {"connector": "github.issues", "rotated": True}})
    assert updated.status_code == 200
    assert updated.json()["secret"]["metadata"] == {"connector": "github.issues", "rotated": True}

    deleted = client.delete("/secrets/github.token", headers=ALPHA_HEADERS)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": "github.token"}
    assert client.get("/secrets", headers=ALPHA_HEADERS).json()["secrets"] == []
    assert db_session.query(SecretRecord).count() == 0
    audit_types = [event.event_type for event in db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()]
    assert audit_types.count("secret_stored") == 2
    assert "secret_deleted" in audit_types


def test_secret_lifecycle_api_missing_delete_fails_closed(client: Any) -> None:
    deleted = client.delete("/secrets/missing.token", headers=ALPHA_HEADERS)

    assert deleted.status_code == 404
    assert deleted.json()["detail"]["message"] == "secret not found"
