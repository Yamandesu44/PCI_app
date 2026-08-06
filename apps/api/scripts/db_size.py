"""アプリの PostgreSQL の容量を測る。

移行先の無料枠（例: 500MB）に何年収まるかを判断するための材料。
JRA は年間約3,400レース走るので、現在のレース数から年あたりの増加率が出せる。

**取り込み元の mykeibadb（MySQL）ではなく、アプリ本体の PostgreSQL を見る。**
接続先は `DATABASE_URL` に従うので、アプリと同じDBを確実に測れる。

    cd apps/api
    .venv/bin/python -m scripts.db_size
"""

from __future__ import annotations

from sqlalchemy import text

from pci.config.settings import get_settings
from pci.infrastructure.database.session import build_engine

# 1テーブルあたりの表示行数。全部出しても判断には使わない。
_TOP_N = 15


def main() -> None:
    engine = build_engine(get_settings().database_url)
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        ).scalar_one()
        print(f"データベース全体: {total}")

        print("\n■ 大きいテーブル（インデックス込み）")
        rows = conn.execute(
            text(
                """
                SELECT relname,
                       pg_size_pretty(pg_total_relation_size(relid)) AS total,
                       n_live_tup AS rows
                FROM pg_catalog.pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT :limit
                """
            ),
            {"limit": _TOP_N},
        ).all()
        print(f"  {'テーブル':<28}{'サイズ':>12}{'概算行数':>12}")
        for relname, size, live_rows in rows:
            print(f"  {relname:<28}{size:>12}{live_rows:>12,}")

        # 増加率の見積もりに使う。JRA は年間約3,400レース。
        race_count = conn.execute(text("SELECT count(*) FROM races")).scalar_one()
        print(f"\n■ 収録レース数: {race_count:,}")
        if race_count:
            years = race_count / 3400
            print(f"  概算で約 {years:.1f} 年分。1年あたり全体の約 {100 / years:.0f}% ずつ増える。")

        print(
            "\n※ 実際の増加はマート層の再計算やログの蓄積でも進む。"
            "\n※ 移行先の無料枠と比べるときは、今収まるかではなく数年後も収まるかで見ること。"
        )


if __name__ == "__main__":
    main()
