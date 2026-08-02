"""取り込み元mykeibadbの事前接続確認の単体テスト（実DB不要）。

pymysql は任意の extra（`.[mysql]`）で、CI では入っていない。
`check_mykeibadb` は import を関数内で行うため、偽のモジュールを差し込んで検証する。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.check_mykeibadb import _classify, check  # noqa: E402


class _FakeCursor:
    def __init__(self, tables: list[tuple[str, ...]]) -> None:
        self._tables = tables

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        assert sql == "SHOW TABLES"

    def fetchall(self) -> list[tuple[str, ...]]:
        return self._tables


class _FakeConnection:
    def __init__(self, tables: list[tuple[str, ...]]) -> None:
        self._tables = tables
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._tables)

    def close(self) -> None:
        self.closed = True


def _install_fake_pymysql(
    monkeypatch: pytest.MonkeyPatch,
    *,
    connect: Any,
) -> None:
    module = types.ModuleType("pymysql")
    module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pymysql", module)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """.env や実行環境の MYKEIBADB_* に結果が左右されないようにする。"""
    for key in (
        "MYKEIBADB_DSN",
        "MYKEIBADB_HOST",
        "MYKEIBADB_PORT",
        "MYKEIBADB_USER",
        "MYKEIBADB_PASSWORD",
        "MYKEIBADB_DATABASE",
        "MYKEIBADB_CHARSET",
    ):
        monkeypatch.delenv(key, raising=False)


class TestClassify:
    def test_connection_refused_points_at_the_stopped_service(self) -> None:
        # 2026-08-02 に実際に出たエラー。ユーザーが最初に見る文言なので固定する。
        message = _classify(OSError(2003, "Can't connect to MySQL server on 'localhost'"))
        assert "MySQL80" in message
        assert "services.msc" in message
        assert "§6.1" in message

    def test_access_denied_points_at_the_password(self) -> None:
        message = _classify(OSError(1045, "Access denied for user 'root'@'localhost'"))
        assert "MYKEIBADB_PASSWORD" in message
        assert "§6.2" in message

    def test_unknown_database_points_at_the_database_name(self) -> None:
        message = _classify(OSError(1049, "Unknown database 'mykeibadb'"))
        assert "MYKEIBADB_DATABASE" in message

    def test_unexpected_error_still_returns_guidance(self) -> None:
        assert _classify(RuntimeError("boom"))
        # args が空でも例外にならないこと（分類できないだけ）
        assert _classify(RuntimeError())


class TestCheck:
    def test_missing_pymysql_reports_the_install_command(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setitem(sys.modules, "pymysql", None)

        assert check() == 1
        assert "pip install" in capsys.readouterr().out

    def test_connection_failure_prints_the_matching_fix(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _connect(**kwargs: Any) -> Any:
            raise OSError(2003, "Can't connect to MySQL server on 'localhost'")

        _install_fake_pymysql(monkeypatch, connect=_connect)

        assert check() == 1
        out = capsys.readouterr().out
        assert "接続できません" in out
        assert "net start MySQL80" in out

    def test_empty_database_is_not_reported_as_healthy(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """テーブル0件は「取り込みが一度も走っていない」状態で、正常ではない。"""
        _install_fake_pymysql(monkeypatch, connect=lambda **kw: _FakeConnection([]))

        assert check() == 1
        assert "テーブルが1つもありません" in capsys.readouterr().out

    def test_successful_connection_reports_table_count(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_fake_pymysql(
            monkeypatch, connect=lambda **kw: _FakeConnection([("RACE_SHOSAI",), ("UMA_RACE",)])
        )

        assert check() == 0
        assert "テーブル 2 件" in capsys.readouterr().out

    def test_connection_is_closed_even_when_the_query_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """接続を開いたまま抜けると、以降の実行が接続数上限に当たりうる。"""
        opened: list[_FakeConnection] = []

        class _BrokenConnection(_FakeConnection):
            def cursor(self) -> _FakeCursor:
                raise RuntimeError("query failed")

        def _connect(**kwargs: Any) -> Any:
            connection = _BrokenConnection([])
            opened.append(connection)
            return connection

        _install_fake_pymysql(monkeypatch, connect=_connect)

        with pytest.raises(RuntimeError):
            check()
        assert opened and opened[0].closed

    def test_uses_the_same_env_config_as_the_batch(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """batch.py と同じ MyKeibaDbConfig.from_env() を通すことを固定する。"""
        monkeypatch.setenv("MYKEIBADB_HOST", "db.example")
        monkeypatch.setenv("MYKEIBADB_PORT", "3307")
        monkeypatch.setenv("MYKEIBADB_USER", "someone")
        monkeypatch.setenv("MYKEIBADB_DATABASE", "otherdb")
        seen: dict[str, Any] = {}

        def _connect(**kwargs: Any) -> Any:
            seen.update(kwargs)
            return _FakeConnection([("T",)])

        _install_fake_pymysql(monkeypatch, connect=_connect)

        assert check() == 0
        assert seen["host"] == "db.example"
        assert seen["port"] == 3307
        assert seen["user"] == "someone"
        assert seen["database"] == "otherdb"
        assert "someone@db.example:3307/otherdb" in capsys.readouterr().out
