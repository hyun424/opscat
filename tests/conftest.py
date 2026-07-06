"""Shared test helpers for OpsCat contract and eval tests."""

from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db

REQUIRED_ENDPOINTS = {
    "health": ("GET", "/health"),
    "mock_alert": ("POST", "/webhooks/alerts/mock"),
    "list_incidents": ("GET", "/incidents"),
    "get_incident": ("GET", "/incidents/{incident_id}"),
    "investigate": ("POST", "/incidents/{incident_id}/investigate"),
    "approval_decision": ("POST", "/approvals/{action_id}"),
    "report": ("GET", "/incidents/{incident_id}/report"),
    "night_autopilot": ("POST", "/night-autopilot/simulate"),
}


@pytest.fixture(scope="session")
def app_module() -> Any:
    os.environ.setdefault("OPSCAT_MODE", "test")
    db_file = tempfile.NamedTemporaryFile(prefix="opscat-test-", suffix=".db", delete=False)
    db_file.close()
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_file.name}")
    for secret_name in ("SENTRY_AUTH_TOKEN", "GITHUB_TOKEN", "SLACK_BOT_TOKEN"):
        os.environ.pop(secret_name, None)
    try:
        return importlib.import_module("app.main")
    except ModuleNotFoundError as exc:
        pytest.skip(f"FastAPI app scaffold is not available yet: {exc}")


@pytest.fixture(scope="session")
def app(app_module: Any) -> Any:
    application = getattr(app_module, "app", None)
    if application is None:
        pytest.skip("app.main does not expose a FastAPI instance named 'app' yet")
    return application


@pytest.fixture()
def db_session() -> Generator[Session]:
    from app.models import action, evidence, incident, policy, timeline  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session, app: Any) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def route_fingerprint(app: Any) -> set[tuple[str, str]]:
    fingerprints: set[tuple[str, str]] = set()

    def visit(route: Any) -> None:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            for nested in getattr(original_router, "routes", []):
                visit(nested)
            return
        path = getattr(route, "path", "")
        for method in getattr(route, "methods", set()) or set():
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                fingerprints.add((method, path))

    for route in getattr(app, "routes", []):
        visit(route)
    return fingerprints


def assert_no_external_credentials_required() -> None:
    forbidden = ["SENTRY_AUTH_TOKEN", "GITHUB_TOKEN", "SLACK_BOT_TOKEN"]
    assert not any(os.environ.get(name) for name in forbidden), "tests must run without real credentials"
