"""移行元と移行先のDBを突き合わせ、データが欠けていないか確認する。

`pg_restore` は途中で失敗しても**部分的に成功した状態で終わる**ことがある。
外部キーの順序やロールの違いで一部テーブルだけ入らない、という壊れ方が典型で、
アプリを繋いで初めて気付くことになる。移行直後に必ず突き合わせる。

比較するのは全テーブルの行数と、主キーの最大値。行数だけだと「同じ件数だが
中身が違う」を拾えないため、レース系は範囲も見る。

使い方:
    cd apps/api
    # 移行先を DATABASE_URL に、移行元を --source に渡す
    python -m scripts.verify_migration --source "postgresql+pg8000://...元..."

    # 逆向きに確認したい場合は --target で明示できる
    python -m scripts.verify_migration --source "..." --target "..."
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from sqlalchemy import Engine, text

from pci.config.settings import get_settings
from pci.infrastructure.database.session import build_engine


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, help="移行元の接続文字列")
    p.add_argument(
        "--target",
        default=None,
        help="移行先の接続文字列。未指定なら DATABASE_URL を使う。",
    )
    return p.parse_args()


def _table_names(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tablename FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
        ).all()
    return [row[0] for row in rows]


def _row_counts(engine: Engine, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table in tables:
            # テーブル名はカタログ由来なので注入の余地は無いが、識別子は引用する。
            counts[table] = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
    return counts


def _race_key_range(engine: Engine) -> tuple[str | None, str | None]:
    """レースキーの範囲。行数が同じでも期間がずれていれば気付ける。"""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT min(race_key), max(race_key) FROM races")).one()
    return row[0], row[1]


def main() -> None:
    args = _parse_args()
    target_url = args.target or get_settings().database_url

    source = build_engine(args.source)
    target = build_engine(target_url)

    source_tables = _table_names(source)
    target_tables = _table_names(target)

    missing = sorted(set(source_tables) - set(target_tables))
    extra = sorted(set(target_tables) - set(source_tables))

    print("■ テーブルの有無")
    if missing:
        print(f"  移行先に無い: {', '.join(missing)}")
    if extra:
        print(f"  移行先にのみ有る: {', '.join(extra)}")
    if not missing and not extra:
        print(f"  一致（{len(source_tables)} テーブル）")

    shared = sorted(set(source_tables) & set(target_tables))
    source_counts = _row_counts(source, shared)
    target_counts = _row_counts(target, shared)

    print("\n■ 行数")
    print(f"  {'テーブル':<28}{'移行元':>12}{'移行先':>12}{'差':>10}")
    mismatched: list[str] = []
    for table in shared:
        src, tgt = source_counts[table], target_counts[table]
        diff = tgt - src
        mark = "" if diff == 0 else "  ←不一致"
        if diff != 0:
            mismatched.append(table)
        print(f"  {table:<28}{src:>12,}{tgt:>12,}{diff:>+10,}{mark}")

    print("\n■ レースキーの範囲")
    src_range = _race_key_range(source)
    tgt_range = _race_key_range(target)
    print(f"  移行元: {src_range[0]} 〜 {src_range[1]}")
    print(f"  移行先: {tgt_range[0]} 〜 {tgt_range[1]}")
    range_ok = src_range == tgt_range

    print()
    if missing or mismatched or not range_ok:
        print("✗ 差異があります。移行は完了していません。")
        print("  pg_restore のログを確認し、失敗したテーブルを特定してください。")
        raise SystemExit(1)
    print("✓ テーブル・行数・レースキーの範囲がすべて一致しました。")


if __name__ == "__main__":
    main()
