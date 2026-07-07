from __future__ import annotations

import json
from typing import Any

import pytest

from app.models import AuditEvent, SecretRecord
from app.services.authorization import AuthorizationError
from app.services.identity_service import Principal, get_or_create_local_principal
from app.services.secret_service import LocalEncryptedSecretProvider, SecretIntegrityError, SecretNotFoundError


def _principal(db_session: Any, *, workspace: str = "workspace-a", role: str = "admin") -> Principal:
    return get_or_create_local_principal(
        db_session,
        email=f"{role}-{workspace}@example.com",
        tenant_id="tenant-a",
        workspace_id=workspace,
        role=role,
    )


def test_local_secret_provider_round_trips_without_storing_plaintext(db_session: Any) -> None:
    principal = _principal(db_session)
    provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")

    ref = provider.put_secret(db_session, principal, "sentry.token", "sntrys_secret_value", metadata={"connector": "sentry", "owner_email": "ops@example.com"})
    value = provider.get_secret(db_session, principal, "sentry.token")

    assert value == "sntrys_secret_value"
    assert ref.name == "sentry.token"
    assert ref.provider == "local-envelope"
    assert "ops@example.com" not in str(ref.metadata)
    stored = db_session.query(SecretRecord).one()
    assert stored.ciphertext != "sntrys_secret_value"
    assert "sntrys_secret_value" not in json.dumps(stored.secret_metadata, sort_keys=True)
    audit_payload = json.dumps([event.event_metadata for event in db_session.query(AuditEvent).all()], sort_keys=True)
    assert "sntrys_secret_value" not in audit_payload
    assert "ops@example.com" not in audit_payload


def test_secret_refs_do_not_expose_secret_values(db_session: Any) -> None:
    principal = _principal(db_session)
    provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    provider.put_secret(db_session, principal, "github.token", "ghp_super_secret", metadata={"connector": "github"})

    refs = provider.list_refs(db_session, principal)

    assert [(ref.name, ref.provider, ref.metadata["connector"]) for ref in refs] == [("github.token", "local-envelope", "github")]
    assert "ghp_super_secret" not in str(refs)


def test_secret_scope_and_role_fail_closed(db_session: Any) -> None:
    admin = _principal(db_session, workspace="workspace-a", role="admin")
    other = _principal(db_session, workspace="workspace-b", role="admin")
    viewer = _principal(db_session, workspace="workspace-a", role="viewer")
    provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    provider.put_secret(db_session, admin, "slack.token", "xoxb-secret")

    with pytest.raises(SecretNotFoundError):
        provider.get_secret(db_session, other, "slack.token")
    with pytest.raises(AuthorizationError):
        provider.put_secret(db_session, viewer, "slack.token", "new-secret")
    with pytest.raises(AuthorizationError):
        provider.delete_secret(db_session, viewer, "slack.token")


def test_wrong_master_key_or_scope_fails_integrity(db_session: Any) -> None:
    principal = _principal(db_session)
    provider = LocalEncryptedSecretProvider(master_key="correct-master-key")
    provider.put_secret(db_session, principal, "sentry.token", "sntrys_secret_value")

    wrong_key = LocalEncryptedSecretProvider(master_key="wrong-master-key")
    with pytest.raises(SecretIntegrityError):
        wrong_key.get_secret(db_session, principal, "sentry.token")


def test_delete_secret_removes_record_and_audits(db_session: Any) -> None:
    principal = _principal(db_session)
    provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    provider.put_secret(db_session, principal, "sentry.token", "secret")

    provider.delete_secret(db_session, principal, "sentry.token")

    assert db_session.query(SecretRecord).count() == 0
    assert "secret_deleted" in [event.event_type for event in db_session.query(AuditEvent).all()]
