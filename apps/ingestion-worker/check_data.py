"""取り込み結果の確認用診断スクリプト（読み取り専用）。

PostgreSQL の races / race_entries を集計し、1年分の取り込みが
どこまで成功したか（出走馬・確定成績・PCI が入っているか）を可視化する。

使い方:
    python check_data.py
    python check_data.py --month   # 月別の内訳も表示

必要パッケージ:
    pip install psycopg2-binary python-dotenv
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# pg8000 形式「postgresql+pg8000://...」を psycopg2 用「postgresql://...」に変換する。
_PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+pg8000://pci:pci_dev@localhost:5432/pci_dev",
).replace("postgresql+pg8000://", "postgresql://")


def _pg_conn():
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 が見つかりません。pip install psycopg2-binary を実行してください。", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(_PG_URL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", action="store_true", help="月別の内訳も表示する")
    args = parser.parse_args()

    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            # ----- 全体サマリ -----
            cur.execute("SELECT COUNT(*) FROM races")
            total_races = cur.fetchone()[0]

            cur.execute("SELECT status, COUNT(*) FROM races GROUP BY status ORDER BY status")
            by_status = cur.fetchall()

            cur.execute("SELECT COUNT(DISTINCT race_key) FROM race_entries")
            races_with_entries = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM race_entries")
            total_entries = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM race_entries WHERE pci_actual IS NOT NULL")
            entries_with_pci = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM races WHERE rpci_actual IS NOT NULL")
            races_with_rpci = cur.fetchone()[0]

            cur.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
            date_min, date_max = cur.fetchone()

            print("=" * 56)
            print("  取り込み結果サマリ（PostgreSQL）")
            print("=" * 56)
            print(f"  レース総数           : {total_races:>8,}")
            print(f"  期間                 : {date_min} 〜 {date_max}")
            print("  ステータス別:")
            for status, count in by_status:
                print(f"      {status:<16}: {count:>8,}")
            print(f"  出走馬ありレース数   : {races_with_entries:>8,}")
            print(f"  出走馬エントリ総数   : {total_entries:>8,}")
            print(f"  PCI算出済みエントリ  : {entries_with_pci:>8,}")
            print(f"  RPCI算出済みレース   : {races_with_rpci:>8,}")
            print("=" * 56)

            if total_races and races_with_entries == 0:
                print("\n  ⚠ 出走馬が1件も入っていません。")
                print("    → SE(馬毎レース情報)テーブルの取り込みに失敗しています。")

            # ----- 月別内訳 -----
            if args.month:
                cur.execute(
                    """
                    SELECT
                        SUBSTRING(race_key, 1, 6)                       AS ym,
                        COUNT(*)                                        AS races,
                        COUNT(*) FILTER (WHERE rpci_actual IS NOT NULL) AS with_rpci
                    FROM races
                    GROUP BY ym
                    ORDER BY ym
                    """
                )
                rows = cur.fetchall()
                # 出走馬ありレース数を月別に取る
                cur.execute(
                    """
                    SELECT SUBSTRING(race_key, 1, 6) AS ym, COUNT(DISTINCT race_key)
                    FROM race_entries
                    GROUP BY ym
                    """
                )
                entries_by_month = dict(cur.fetchall())

                print("\n  月別内訳:")
                print(f"    {'年月':<8}{'レース':>8}{'出走表あり':>12}{'成績あり':>10}")
                print(f"    {'-' * 38}")
                for ym, races, with_rpci in rows:
                    ym_label = f"{ym[:4]}/{ym[4:6]}"
                    with_entries = entries_by_month.get(ym, 0)
                    print(f"    {ym_label:<8}{races:>8,}{with_entries:>12,}{with_rpci:>10,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
