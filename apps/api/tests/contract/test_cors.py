"""CORS 許可オリジンと、無認証公開の警告の契約テスト。

web は Next.js のサーバコンポーネントから API を呼ぶため、通常の動作に CORS は
要らない（`apps/web/src/lib/api.ts`）。以前は `allow_origins=["*"]` だったが、
利点が無い一方で、公開時は任意のサイトから JRA-VAN 由来のデータをブラウザ経由で
読み出せる状態になっていた（CLAUDE.md「生データ再配布は禁止前提」）。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pci.config.settings import Settings
from pci.presentation.app import create_app


def _settings(origins: str, token: str | None = None) -> MagicMock:
    """`cors_origin_list` は実装を通し、他は差し替える。"""
    settings = MagicMock()
    settings.cors_allow_origins = origins
    settings.cors_origin_list.return_value = Settings(cors_allow_origins=origins).cors_origin_list()
    settings.public_api_token = token
    return settings


def _allowed_origin(origins: str, request_origin: str) -> str | None:
    with patch("pci.presentation.app.get_settings", return_value=_settings(origins)):
        client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": request_origin})
    return response.headers.get("access-control-allow-origin")


class TestCorsOrigins:
    def test_configured_origin_is_allowed(self) -> None:
        assert (
            _allowed_origin("https://example.test", "https://example.test")
            == "https://example.test"
        )

    def test_other_origins_are_not_allowed(self) -> None:
        assert _allowed_origin("https://example.test", "https://evil.test") is None

    def test_empty_setting_disables_cors_entirely(self) -> None:
        assert _allowed_origin("", "http://localhost:3000") is None

    def test_wildcard_is_not_the_default(self) -> None:
        """既定を全許可へ戻さない。戻ると誰でもブラウザから読める状態になる。"""
        assert "*" not in Settings().cors_origin_list()

    def test_default_covers_local_development_only(self) -> None:
        assert Settings().cors_origin_list() == [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    def test_blank_entries_are_ignored(self) -> None:
        settings = Settings(cors_allow_origins=" https://a.test , , https://b.test ")

        assert settings.cors_origin_list() == ["https://a.test", "https://b.test"]


class TestOpenApiWarning:
    """認証なしで全公開のまま黙って起動しない。"""

    def test_warns_when_the_public_api_has_no_token(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.WARNING, logger="pci.presentation.app"),
            patch(
                "pci.presentation.app.get_settings",
                return_value=_settings("http://localhost:3000", token=None),
            ),
        ):
            create_app()

        assert "PUBLIC_API_TOKEN" in caplog.text

    def test_does_not_warn_when_the_token_is_set(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.WARNING, logger="pci.presentation.app"),
            patch(
                "pci.presentation.app.get_settings",
                return_value=_settings("http://localhost:3000", token="secret"),
            ),
        ):
            create_app()

        assert "PUBLIC_API_TOKEN" not in caplog.text
