"""公開参照APIのレート制限の契約テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from pci.presentation.app import create_app
from tests.contract.conftest import override_dependencies
from tests.unit.application.fake_repository import FakeRaceRepository


def _settings(
    limit: int,
    token: str | None = None,
    trusted_proxies: int = 0,
) -> MagicMock:
    settings = MagicMock()
    settings.rate_limit_per_minute = limit
    settings.rate_limit_trusted_proxies = trusted_proxies
    settings.public_api_token = token
    settings.cors_origin_list.return_value = []
    return settings


@contextmanager
def _client(repo: FakeRaceRepository, **kwargs: object) -> Iterator[TestClient]:
    """設定を差し替えた app を、契約テスト共通の Fake 依存で組む。

    差し替えはリクエスト中も効かせる必要がある。トークン検査の middleware は
    起動時ではなくリクエストごとに設定を読むため、`create_app` の間だけ差し替えても
    認証の挙動は再現できない。
    """
    with patch("pci.presentation.app.get_settings", return_value=_settings(**kwargs)):  # type: ignore[arg-type]
        app = create_app()
        override_dependencies(app, repo)
        yield TestClient(app)


class TestRateLimit:
    def test_allows_requests_up_to_the_limit(self, repo: FakeRaceRepository) -> None:
        with _client(repo, limit=3) as client:
            codes = [client.get("/api/v1/races").status_code for _ in range(3)]

        assert codes == [200, 200, 200]

    def test_rejects_with_429_and_retry_after(self, repo: FakeRaceRepository) -> None:
        with _client(repo, limit=2) as client:
            for _ in range(2):
                client.get("/api/v1/races")

            response = client.get("/api/v1/races")

        assert response.status_code == 429
        assert response.headers["cache-control"] == "no-store"
        # 秒数として読める値を返す。0 は「すぐ再試行してよい」と誤解されるため出さない。
        assert int(response.headers["retry-after"]) >= 1

    def test_zero_disables_the_limit(self, repo: FakeRaceRepository) -> None:
        with _client(repo, limit=0) as client:
            codes = {client.get("/api/v1/races").status_code for _ in range(50)}

        assert codes == {200}

    def test_health_endpoints_are_not_limited(self, repo: FakeRaceRepository) -> None:
        """監視系まで止めると、負荷時に死活判定ができなくなる。"""
        with _client(repo, limit=1) as client:
            client.get("/api/v1/races")  # 上限を使い切る

            assert client.get("/health").status_code == 200

    def test_ingest_endpoints_are_not_limited(self, repo: FakeRaceRepository) -> None:
        """取り込みは別トークンで守られており、バッチ投入を止めたくない。"""
        with _client(repo, limit=1) as client:
            client.get("/api/v1/races")

            # 認証で弾かれるにせよ、429 ではないこと（レート制限の対象外）。
            assert client.get("/internal/ingest/incomplete-races").status_code != 429

    def test_runs_before_the_token_check(self, repo: FakeRaceRepository) -> None:
        """安いはじき方を先にする。トークン比較まで到達させない。

        逆順だと、認証を持たない相手からの連打でも毎回トークン比較まで走る。
        """
        with _client(repo, limit=1, token="secret") as client:
            first = client.get("/api/v1/races")  # 401（上限は消費される）
            second = client.get("/api/v1/races")

        assert first.status_code == 401
        assert second.status_code == 429

    def test_separate_clients_have_separate_budgets(self, repo: FakeRaceRepository) -> None:
        """信頼できるプロキシ段数を宣言していれば、転送元ごとに数える。"""
        headers_a = {"X-Forwarded-For": "198.51.100.7, 10.0.0.1"}
        headers_b = {"X-Forwarded-For": "198.51.100.8, 10.0.0.1"}

        with _client(repo, limit=1, trusted_proxies=1) as client:
            assert client.get("/api/v1/races", headers=headers_a).status_code == 200
            assert client.get("/api/v1/races", headers=headers_b).status_code == 200
            assert client.get("/api/v1/races", headers=headers_a).status_code == 429

    def test_forwarded_header_is_ignored_without_declared_proxies(
        self, repo: FakeRaceRepository
    ) -> None:
        """段数を宣言していなければ、ヘッダを変えても別クライアント扱いにしない。

        これを許すと、ヘッダを付け替えるだけで無制限に叩ける。
        """
        with _client(repo, limit=1, trusted_proxies=0) as client:
            client.get("/api/v1/races", headers={"X-Forwarded-For": "1.1.1.1"})

            response = client.get("/api/v1/races", headers={"X-Forwarded-For": "2.2.2.2"})

        assert response.status_code == 429
