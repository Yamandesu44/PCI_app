"""DB エンジンの構成テスト。

サーバーレス実行環境（Cloud Run）では、既定のままだと2つの形で壊れる。
どちらも「最初のリクエストだけ失敗する」類で気付きにくいので、設定を固定する。
"""

from __future__ import annotations

from sqlalchemy.pool import QueuePool

from pci.infrastructure.database.session import build_engine

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
