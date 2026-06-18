"""ヘルスチェック / OpenAPI 契約テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_exposes_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/races/{race_key}/forecast" in paths
    assert "/api/v1/races/{race_key}" in paths
    assert "/health" in paths
