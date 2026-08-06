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
        # 行数は count(*) で実測する。`pg_stat_user_tables.n_live_tup` は
        # ANALYZE / autovacuum が走るまで 0 のままで、取り込み直後は当てにならない。
        rows = conn.execute(
            text(
                """
                SELECT relname,
                       pg_size_pretty(pg_total_relation_size(relid)) AS total,
                       pg_total_relation_size(relid) AS bytes
                FROM pg_catalog.pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT :limit
                """
            ),
            {"limit": _TOP_N},
        ).all()
        print(f"  {'テーブル':<28}{'サイズ':>12}{'行数':>12}{'1行あたり':>12}")
        for relname, size, total_bytes in rows:
            n = conn.execute(text(f'SELECT count(*) FROM "{relname}"')).scalar_one()
            per_row = f"{total_bytes / n / 1024:.2f} KB" if n else "-"
            print(f"  {relname:<28}{size:>12}{n:>12,}{per_row:>12}")

        # 増加率の見積もりに使う。JRA は年間約3,400レース。
        race_count = conn.execute(text("SELECT count(*) FROM races")).scalar_one()
        print(f"\n■ 収録レース数: {race_count:,}")
        if race_count:
            years = race_count / 3400
            print(f"  概算で約 {years:.1f} 年分。1年あたり全体の約 {100 / years:.0f}% ずつ増える。")

        # mart 層は model_version が主キーに入っており、世代を上げるたびに
        # 行が「増える」（更新ではない）。容量見積もりで見落としやすい。
        versions = conn.execute(
            text("SELECT model_version, count(*) FROM pace_fit GROUP BY 1 ORDER BY 2 DESC")
        ).all()
        if versions:
            print("\n■ mart 層（pace_fit）の世代別行数")
            for version, count in versions:
                print(f"  {version:<28}{count:>12,}")
            print("  ※ model_version は主キーの一部。世代を上げると行が増える（更新ではない）。")
            print("     古い世代を残し続けると、コアデータより速く容量を食う。")

        print("\n※ 移行先の無料枠と比べるときは、今収まるかではなく数年後も収まるかで見ること。")


if __name__ == "__main__":
    main()
