"""DB エンジンの構成テスト。

サーバーレス実行環境（Cloud Run）では、既定のままだと2つの形で壊れる。
どちらも「最初のリクエストだけ失敗する」類で気付きにくいので、設定を固定する。
"""

from __future__ import annotations

import logging
import ssl
from pathlib import Path

import pytest
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import QueuePool

from pci.config.settings import get_settings
from pci.infrastructure.database.session import (
    _split_pg8000_ssl,
    build_engine,
    resolve_migration_url,
)

_URL = "postgresql+pg8000://u:p@localhost:5432/db"


class TestBuildEngine:
    def test_pool_is_small_enough_to_survive_scaling_out(self) -> None:
        """SQLAlchemy 既定の 5+10=15本/プロセスは、台数倍すると無料枠の上限を超える。

        max-instances=3 なら 45本。上限に当たると新しいインスタンスがDBへ
        一切繋げなくなる。
        """
        engine = build_engine(_URL)

        pool = engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() + pool._max_overflow <= 5

    def test_pre_ping_is_enabled(self) -> None:
        """サーバーレスDBはアイドルで自動停止する。死んだ接続をそのまま使わない。"""
        engine = build_engine(_URL)

        assert engine.pool._pre_ping is True

    def test_connections_are_recycled_before_the_far_end_drops_them(self) -> None:
        engine = build_engine(_URL)

        assert 0 < engine.pool._recycle <= 1800

    def test_pool_sizing_is_overridable(self) -> None:
        """常駐環境へ移す場合など、絞る必要が無いときに広げられること。"""
        engine = build_engine(_URL, pool_size=10, max_overflow=20)

        assert engine.pool.size() == 10
        assert engine.pool._max_overflow == 20


class TestPg8000Ssl:
    """`sslmode` の翻訳。

    pg8000 は `sslmode` を受け取れず、マネージドDBが配る接続文字列
    （`?sslmode=require` 付き）をそのまま使うと接続自体が失敗する。
    psycopg2 なら通るため、ドライバを変えた途端に壊れる類の落とし穴。
    """

    @staticmethod
    def _translate(url: str) -> tuple[URL, dict[str, object]]:
        return _split_pg8000_ssl(make_url(url))

    def test_sslmode_is_stripped_from_the_url(self) -> None:
        """ここが漏れると pg8000 が TypeError を投げて接続できない。"""
        stripped, _ = self._translate(f"{_URL}?sslmode=require")

        assert "sslmode" not in stripped.query

    def test_require_encrypts_without_verifying(self) -> None:
        """libpq の require は「暗号化するが検証しない」。同じ意味に揃える。"""
        _, args = self._translate(f"{_URL}?sslmode=require")

        context = args["ssl_context"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False

    def test_verify_full_checks_the_certificate_and_hostname(self) -> None:
        _, args = self._translate(f"{_URL}?sslmode=verify-full")

        context = args["ssl_context"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True

    def test_verify_ca_checks_the_certificate_only(self) -> None:
        _, args = self._translate(f"{_URL}?sslmode=verify-ca")

        context = args["ssl_context"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is False

    def test_disable_uses_no_ssl(self) -> None:
        _, args = self._translate(f"{_URL}?sslmode=disable")

        assert args == {}

    def test_no_sslmode_leaves_the_connection_untouched(self) -> None:
        """手元の docker-compose など、TLS 無しの接続を壊さない。"""
        _, args = self._translate(_URL)

        assert args == {}

    def test_unknown_sslmode_is_rejected(self) -> None:
        """黙って無防備な接続へ倒さない。"""
        with pytest.raises(ValueError, match="sslmode"):
            self._translate(f"{_URL}?sslmode=nonsense")

    def test_build_engine_accepts_a_managed_database_url(self) -> None:
        """接続文字列をそのまま貼っても組み立てが通ること（配線の確認）。"""
        engine = build_engine(f"{_URL}?sslmode=require")

        assert "sslmode" not in engine.url.query


class TestUnencryptedWarning:
    """マネージドDBへ平文で繋ごうとしていることに気付けるか。

    接続は成功し、動作も変わらない。警告が無ければ、資格情報とデータが平文で
    流れ続けていることに気付く機会が無い。
    """

    def test_remote_host_without_sslmode_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            build_engine("postgresql+pg8000://u:p@db.example.supabase.com:5432/postgres")

        assert "sslmode" in caplog.text

    def test_remote_host_with_sslmode_is_quiet(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            build_engine(
                "postgresql+pg8000://u:p@db.example.supabase.com:5432/postgres?sslmode=require"
            )

        assert caplog.text == ""

    def test_local_host_is_quiet(self, caplog: pytest.LogCaptureFixture) -> None:
        """手元の開発を騒がしくしない。公衆網を通らないため。"""
        with caplog.at_level(logging.WARNING):
            build_engine(_URL)

        assert caplog.text == ""

    def test_docker_compose_service_name_is_quiet(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            build_engine("postgresql+pg8000://u:p@db:5432/pci_dev")

        assert caplog.text == ""


class TestMigrationsShareTheSamePreparation:
    """alembic が独自にエンジンを組んでいないこと。

    SSL の翻訳を通らない経路が1つでもあると、**アプリは繋がるのに
    マイグレーションだけ落ちる**。実際に Supabase へ繋ぐ場面でこれが起きた。
    経路を増やしたくなったら `prepare_connection` を通すこと。
    """

    def _env_source(self) -> str:
        env_py = Path(__file__).resolve().parents[4] / "alembic" / "env.py"
        return env_py.read_text(encoding="utf-8")

    def test_env_py_uses_the_shared_preparation(self) -> None:
        assert "prepare_connection" in self._env_source()

    def test_env_py_does_not_build_its_own_engine_from_config(self) -> None:
        assert "engine_from_config" not in self._env_source()

    def test_env_py_resolves_the_target_through_the_shared_resolver(self) -> None:
        """接続先の決定を env.py の中に書き直さないこと。

        この分岐は二度事故を起こしている（`resolve_migration_url` の docstring 参照）。
        env.py はテストから import できない（読み込むだけでマイグレーションが走る）ので、
        ロジックを外へ出して**振る舞いをテストできる形**に保つ。
        """
        source = self._env_source()
        assert "resolve_migration_url" in source
        assert "get_settings" not in source


class TestResolveMigrationUrl:
    """どのDBへ流すかを決める分岐。**取り違えると黙って別のDBが変わる。**"""

    def test_explicit_url_wins(self) -> None:
        """呼び出し元が明示した接続先を使う。

        統合テストは `Config.set_main_option("sqlalchemy.url", ...)` で
        testcontainers の接続先を渡す。ここを無視すると全件が既定の
        localhost:5432 へ向かい、CI が15コミット連続で赤いままになった。
        """
        assert (
            resolve_migration_url("postgresql+pg8000://u:p@container:55432/test")
            == "postgresql+pg8000://u:p@container:55432/test"
        )

    def test_falls_back_to_settings_when_not_specified(self) -> None:
        for empty in (None, "", "   "):
            assert resolve_migration_url(empty) == get_settings().database_url

    def test_strips_surrounding_whitespace(self) -> None:
        assert resolve_migration_url("  postgresql+pg8000://u:p@h:5432/d  ") == (
            "postgresql+pg8000://u:p@h:5432/d"
        )

    def test_alembic_ini_is_ascii_only(self) -> None:
        """alembic はこのファイルを**ロケールの文字コード**で読む。

        日本語版 Windows では cp932 になり、UTF-8 の日本語を入れると
        コマンド自体が `UnicodeDecodeError` で起動しない。コメントは英語で書く。
        """
        ini = Path(__file__).resolve().parents[4] / "alembic.ini"
        ini.read_bytes().decode("ascii")

    def test_alembic_ini_has_no_fallback_target(self) -> None:
        """設定が拾えなかったときに、黙って別のDBへ流れる先を残さない。"""
        ini = Path(__file__).resolve().parents[4] / "alembic.ini"
        for line in ini.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("sqlalchemy.url"):
                assert line.split("=", 1)[1].strip() == ""
