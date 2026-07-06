"""Shared test helpers for OpsCat contract and eval tests."""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from typing import Any

import pytest


REQUIRED_ENDPOINTS = {
    "health": ("GET", "/health"),
    "mock_alert": ("POST", "/webhooks/alerts/mock"),
    "list_incidents": ("GET", "/incidents"),
    "get_incident": ("GET", "/incidents/{incident_id}"),
    "investigate": ("POST", "/incidents/{incident_id}/investigate"),
    "approve_action": ("POST", "/incidents/{incident_id}/actions/{action_id}/approve"),
    "reject_action": ("POST", "/incidents/{incident_id}/actions/{action_id}/reject"),
    "verify": ("POST", "/incidents/{incident_id}/verify"),
    "report": ("GET", "/incidents/{incident_id}/report"),
}


@pytest.fixture(scope="session")
def app_module() -> Any:
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
def client(app: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    # Keep tests independent from developer machines and production credentials.
    db_path = tmp_path / "opscat-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("OPSCAT_MODE", "test")
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:
        pytest.skip(f"FastAPI test dependencies are not installed yet: {exc}")

    with TestClient(app) as test_client:
        yield test_client


def route_fingerprint(app: Any) -> set[tuple[str, str]]:
    fingerprints: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "")
        for method in getattr(route, "methods", set()) or set():
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                fingerprints.add((method, path))
    return fingerprints


def assert_no_external_credentials_required() -> None:
    forbidden = ["SENTRY_AUTH_TOKEN", "GITHUB_TOKEN", "SLACK_BOT_TOKEN"]
    assert not any(os.environ.get(name) for name in forbidden), "tests must run without real credentials"
