"""指定日付範囲のレースを PostgreSQL から削除して再取り込みの準備をする。

使い方:
    # 確認のみ（削除なし）
    python clean_races.py --date-from 20260614 --date-to 20260629 --dry-run

    # 実際に削除
    python clean_races.py --date-from 20260614 --date-to 20260629

    # 特別登録レースだけを削除（重複解消目的）
    python clean_races.py --date-from 20260627 --date-to 20260629 --tokubetsu-only

必要パッケージ:
    pip install psycopg2-binary python-dotenv
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

_PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+pg8000://pci:pci_dev@localhost:5432/pci_dev",
).replace("postgresql+pg8000://", "postgresql://")


def _pg_conn():
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 が見つかりません。pip install psycopg2-binary を実行してください。",
              file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(_PG_URL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-from", required=True, help="開始日 YYYYMMDD")
    parser.add_argument("--date-to", required=True, help="終了日 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（削除しない）")
    parser.add_argument(
        "--tokubetsu-only",
        action="store_true",
        help="race_class が '特別登録' を含むものだけ削除（重複解消用）",
    )
    args = parser.parse_args()

    date_from = f"{args.date_from[:4]}-{args.date_from[4:6]}-{args.date_from[6:8]}"
    date_to = f"{args.date_to[:4]}-{args.date_to[4:6]}-{args.date_to[6:8]}"

    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            # 対象レースを表示
            if args.tokubetsu_only:
                cur.execute(
                    """
                    SELECT race_key, race_date, race_class, status
                    FROM races
                    WHERE race_date BETWEEN %s AND %s
                      AND race_class LIKE '%%特別登録%%'
                    ORDER BY race_key
                    """,
                    (date_from, date_to),
                )
            else:
                cur.execute(
                    """
                    SELECT race_key, race_date, race_class, status
                    FROM races
                    WHERE race_date BETWEEN %s AND %s
                    ORDER BY race_key
                    """,
                    (date_from, date_to),
                )
            rows = cur.fetchall()

            if not rows:
                print("削除対象レースはありません。")
                return

            print(f"{'race_key':<18} {'日付':<12} {'クラス':<30} {'状態'}")
            print("-" * 80)
            for race_key, date, cls, status in rows:
                cls_str = (cls or "")[:28]
                print(f"{race_key:<18} {str(date):<12} {cls_str:<30} {status}")
            print(f"\n対象: {len(rows)} レース")

            if args.dry_run:
                print("\n[DRY RUN] 削除は行いません。")
                return

            confirm = input("\n上記を削除しますか？ (yes/no): ").strip().lower()
            if confirm != "yes":
                print("キャンセルしました。")
                return

            # race_entries → races の順で削除（FK 制約）
            race_keys = [r[0] for r in rows]
            cur.execute(
                "DELETE FROM predicted_pace WHERE race_key = ANY(%s)", (race_keys,)
            )
            cur.execute(
                "DELETE FROM pace_fit WHERE race_key = ANY(%s)", (race_keys,)
            )
            cur.execute(
                "DELETE FROM race_entries WHERE race_key = ANY(%s)", (race_keys,)
            )
            cur.execute(
                "DELETE FROM races WHERE race_key = ANY(%s)", (race_keys,)
            )
            conn.commit()
            print(f"\n{len(rows)} レースを削除しました。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
