"""ヘルスチェック / OpenAPI 契約テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pci.infrastructure.database.readiness import DatabaseReadiness
from pci.presentation.app import create_app
from pci.presentation.dependencies import get_database_readiness


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ok(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ready",
        "database": "ok",
        "message": None,
        "action": None,
    }


def test_readiness_reports_outdated_schema() -> None:
    app = create_app()
    app.dependency_overrides[get_database_readiness] = lambda: DatabaseReadiness(
        ready=False, database="schema_outdated"
    )

    with TestClient(app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    assert resp.json()["database"] == "schema_outdated"
    assert "alembic upgrade head" in resp.json()["action"]


def test_openapi_exposes_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/races/{race_key}/forecast" in paths
    assert "/api/v1/races/{race_key}" in paths
    assert "/health" in paths
    assert "/ready" in paths
