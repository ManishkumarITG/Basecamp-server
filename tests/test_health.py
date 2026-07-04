"""Smoke test for the health endpoint.

The DB connection is stubbed so the test runs without a live MongoDB; it verifies
the route wiring and response shape rather than real connectivity.
"""

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    async def fake_connect() -> None:
        return None

    async def fake_close() -> None:
        return None

    async def fake_ping() -> bool:
        return True

    # Stub the lifespan DB hooks and the ping used inside the health route.
    monkeypatch.setattr(main, "connect_to_database", fake_connect)
    monkeypatch.setattr(main, "close_database_connection", fake_close)
    monkeypatch.setattr("app.api.v1.routes.health.ping_database", fake_ping)

    app = main.create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "up"
