"""少人数ロケテスト向け公開API認証の契約テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _settings(token: str | None) -> MagicMock:
    settings = MagicMock()
    settings.public_api_token = token
    return settings


def test_public_api_allows_requests_when_token_is_not_configured(client: TestClient) -> None:
    with patch("pci.presentation.app.get_settings", return_value=_settings(None)):
        response = client.get("/api/v1/races")

    assert response.status_code == 200


def test_public_api_rejects_missing_token_when_configured(client: TestClient) -> None:
    with patch("pci.presentation.app.get_settings", return_value=_settings("secret")):
        response = client.get("/api/v1/races")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["www-authenticate"] == "Bearer"


def test_public_api_rejects_wrong_token(client: TestClient) -> None:
    with patch("pci.presentation.app.get_settings", return_value=_settings("secret")):
        response = client.get(
            "/api/v1/races",
            headers={"Authorization": "Bearer wrong"},
        )

    assert response.status_code == 401


def test_public_api_accepts_matching_token(client: TestClient) -> None:
    with patch("pci.presentation.app.get_settings", return_value=_settings("secret")):
        response = client.get(
            "/api/v1/races",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200


def test_readiness_remains_available_without_public_token(client: TestClient) -> None:
    with patch("pci.presentation.app.get_settings", return_value=_settings("secret")):
        response = client.get("/ready")

    assert response.status_code == 200
