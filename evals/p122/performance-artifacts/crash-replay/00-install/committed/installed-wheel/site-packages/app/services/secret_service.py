"""Secret storage abstraction for connector credentials.

The local provider uses a small stdlib-only authenticated envelope construction
so tests and local demos do not need a cloud secret manager. Production should
swap this provider for an external KMS/secret-manager implementation before any
real customer credentials are stored.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SecretRecord
from app.services.audit_service import record_audit_event
from app.services.authorization import AuthorizationError
from app.services.identity_service import Principal
from app.services.redaction import redact_value

_PROVIDER = "local-envelope"
_DEFAULT_LOCAL_KEY = "local-development-secret-key-change-me"
_DEFAULT_KEY_ALLOWED_MODES = {"local", "local-mock", "test"}


class SecretNotFoundError(KeyError):
    pass


class SecretIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class SecretRef:
    tenant_id: str
    workspace_id: str
    name: str
    provider: str
    metadata: dict[str, object]


class SecretProvider(Protocol):
    def put_secret(self, db: Session, principal: Principal, name: str, value: str, metadata: dict[str, object] | None = None) -> SecretRef: ...

    def get_secret(self, db: Session, principal: Principal, name: str) -> str: ...

    def delete_secret(self, db: Session, principal: Principal, name: str) -> None: ...

    def list_refs(self, db: Session, principal: Principal) -> list[SecretRef]: ...


class LocalEncryptedSecretProvider:
    provider = _PROVIDER

    def __init__(self, master_key: str | None = None) -> None:
        self.master_key = master_key or get_settings().secret_key
        if get_settings().opscat_mode not in _DEFAULT_KEY_ALLOWED_MODES and self.master_key == _DEFAULT_LOCAL_KEY:
            raise ValueError("OPSCAT_SECRET_KEY must be set outside local/local-mock/test mode")

    def put_secret(self, db: Session, principal: Principal, name: str, value: str, metadata: dict[str, object] | None = None) -> SecretRef:
        _require_secret_admin(principal)
        normalized = _normalize_name(name)
        aad = _aad(principal.tenant_id, principal.workspace_id, normalized)
        envelope = _encrypt(value.encode("utf-8"), self.master_key.encode("utf-8"), aad)
        record = _find_record(db, principal, normalized)
        safe_metadata = redact_value(metadata or {})
        if record is None:
            record = SecretRecord(
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                name=normalized,
                provider=self.provider,
                ciphertext=envelope.ciphertext,
                salt=envelope.salt,
                nonce=envelope.nonce,
                tag=envelope.tag,
                secret_metadata=safe_metadata,
            )
            db.add(record)
        else:
            record.ciphertext = envelope.ciphertext
            record.salt = envelope.salt
            record.nonce = envelope.nonce
            record.tag = envelope.tag
            record.secret_metadata = safe_metadata
            record.updated_at = datetime.now(UTC)
            db.add(record)
        db.flush()
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="secret_stored",
            resource_type="secret",
            resource_id=record.id,
            metadata={"name": normalized, "provider": self.provider, "metadata": safe_metadata},
        )
        return _ref(record)

    def get_secret(self, db: Session, principal: Principal, name: str) -> str:
        normalized = _normalize_name(name)
        record = _find_record(db, principal, normalized)
        if record is None:
            record_audit_event(
                db,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                actor=principal.email,
                event_type="secret_missing",
                resource_type="secret",
                resource_id=normalized,
                metadata={"name": normalized},
            )
            raise SecretNotFoundError(normalized)
        aad = _aad(principal.tenant_id, principal.workspace_id, normalized)
        plaintext = _decrypt(
            Envelope(ciphertext=record.ciphertext, salt=record.salt, nonce=record.nonce, tag=record.tag),
            self.master_key.encode("utf-8"),
            aad,
        )
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="secret_accessed",
            resource_type="secret",
            resource_id=record.id,
            metadata={"name": normalized, "provider": record.provider},
        )
        return plaintext.decode("utf-8")

    def delete_secret(self, db: Session, principal: Principal, name: str) -> None:
        _require_secret_admin(principal)
        normalized = _normalize_name(name)
        record = _find_record(db, principal, normalized)
        if record is None:
            raise SecretNotFoundError(normalized)
        db.delete(record)
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="secret_deleted",
            resource_type="secret",
            resource_id=record.id,
            metadata={"name": normalized, "provider": record.provider},
        )

    def list_refs(self, db: Session, principal: Principal) -> list[SecretRef]:
        records = db.query(SecretRecord).filter(SecretRecord.tenant_id == principal.tenant_id, SecretRecord.workspace_id == principal.workspace_id).order_by(SecretRecord.name).all()
        return [_ref(record) for record in records]


@dataclass(frozen=True)
class Envelope:
    ciphertext: str
    salt: str
    nonce: str
    tag: str


def _require_secret_admin(principal: Principal) -> None:
    if not principal.can_admin_workspace:
        raise AuthorizationError("principal cannot manage connector secrets", tenant_id=principal.tenant_id, workspace_id=principal.workspace_id)


def _normalize_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized or any(char.isspace() for char in normalized):
        raise ValueError("secret name must be non-empty and contain no whitespace")
    return normalized


def _find_record(db: Session, principal: Principal, name: str) -> SecretRecord | None:
    return db.query(SecretRecord).filter(SecretRecord.tenant_id == principal.tenant_id, SecretRecord.workspace_id == principal.workspace_id, SecretRecord.name == name).one_or_none()


def _ref(record: SecretRecord) -> SecretRef:
    return SecretRef(
        tenant_id=record.tenant_id,
        workspace_id=record.workspace_id,
        name=record.name,
        provider=record.provider,
        metadata=dict(record.secret_metadata),
    )


def _aad(tenant_id: str, workspace_id: str, name: str) -> bytes:
    return f"{tenant_id}\0{workspace_id}\0{name}".encode()


def _encrypt(plaintext: bytes, master_key: bytes, aad: bytes) -> Envelope:
    salt = os.urandom(16)
    nonce = os.urandom(16)
    key = _derive_key(master_key, salt)
    ciphertext = _xor(plaintext, _keystream(key, nonce, len(plaintext)))
    tag = hmac.new(key, aad + nonce + ciphertext, hashlib.sha256).digest()
    return Envelope(ciphertext=_b64(ciphertext), salt=_b64(salt), nonce=_b64(nonce), tag=_b64(tag))


def _decrypt(envelope: Envelope, master_key: bytes, aad: bytes) -> bytes:
    salt = _unb64(envelope.salt)
    nonce = _unb64(envelope.nonce)
    ciphertext = _unb64(envelope.ciphertext)
    expected_tag = _unb64(envelope.tag)
    key = _derive_key(master_key, salt)
    actual_tag = hmac.new(key, aad + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise SecretIntegrityError("secret envelope authentication failed")
    return _xor(ciphertext, _keystream(key, nonce, len(ciphertext)))


def _derive_key(master_key: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master_key, salt, 200_000, dklen=32)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))
