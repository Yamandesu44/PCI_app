"""確定後レースの race_class（レース名）を MySQL から直接 PostgreSQL へ修正する一回限りのスクリプト。

問題: SE（馬毎レース情報）テーブルに過去レースのデータがなく、
      ingest_entries が「出走馬なし→スキップ」するため race_class が更新されない。
解決: MySQL の race_shosai から正しいレース名を読み、psycopg2 で PostgreSQL を直接 UPDATE する。

使い方:
    python fix_race_class.py --date-from 20260601 --date-to 20260621

必要パッケージ:
    pip install pymysql psycopg2-binary python-dotenv
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

_MYSQL_HOST = os.getenv("MYKEIBADB_HOST", "localhost")
_MYSQL_PORT = int(os.getenv("MYKEIBADB_PORT", "3306"))
_MYSQL_USER = os.getenv("MYKEIBADB_USER", "root")
_MYSQL_PASS = os.getenv("MYKEIBADB_PASSWORD", "")
_MYSQL_DB   = os.getenv("MYKEIBADB_DATABASE", "mykeibadb")

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


def _mysql_conn():
    try:
        import pymysql
    except ImportError:
        print("pymysql が見つかりません。pip install pymysql を実行してください。", file=sys.stderr)
        sys.exit(1)
    return pymysql.connect(
        host=_MYSQL_HOST, port=_MYSQL_PORT,
        user=_MYSQL_USER, password=_MYSQL_PASS,
        database=_MYSQL_DB, charset="utf8mb4",
    )


def fetch_race_names(date_from: str, date_to: str) -> dict[str, str]:
    """MySQL の race_shosai からレース名が空でない行を race_key → name で返す。"""
    conn = _mysql_conn()
    # KAISAI_NEN(4) + KAISAI_GAPPI(4) で YYYYMMDD を合成して比較する。
    sql = """
        SELECT RACE_CODE, KYOSOMEI_HONDAI
        FROM race_shosai
        WHERE CONCAT(KAISAI_NEN, KAISAI_GAPPI) BETWEEN %s AND %s
          AND KYOSOMEI_HONDAI != ''
          AND KYOSOMEI_HONDAI IS NOT NULL
    """
    with conn.cursor() as cur:
        cur.execute(sql, (date_from, date_to))
        rows = cur.fetchall()
    conn.close()
    return {race_code: name for race_code, name in rows if name.strip()}


def fix_postgres(race_name_map: dict[str, str], dry_run: bool) -> None:
    """PostgreSQL の races テーブルを race_class の文字化け行対象に UPDATE する。"""
    if not race_name_map:
        print("修正対象のレース名が MySQL に見つかりませんでした。")
        return

    conn = _pg_conn()
    updated = 0
    skipped = 0
    try:
        with conn.cursor() as cur:
            for race_key, correct_name in sorted(race_name_map.items()):
                # 現在の race_class を取得
                cur.execute("SELECT race_class FROM races WHERE race_key = %s", (race_key,))
                row = cur.fetchone()
                if row is None:
                    skipped += 1
                    continue
                current = row[0] or ""
                if current == correct_name:
                    print(f"  スキップ（既に正しい） {race_key}: {current!r}")
                    skipped += 1
                    continue
                print(f"  UPDATE {race_key}: {current!r} → {correct_name!r}")
                if not dry_run:
                    cur.execute(
                        "UPDATE races SET race_class = %s WHERE race_key = %s",
                        (correct_name, race_key),
                    )
                    updated += 1
                else:
                    updated += 1  # dry-run でもカウント
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}完了: {updated}件 UPDATE, {skipped}件 スキップ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-from", required=True, help="開始日 YYYYMMDD")
    parser.add_argument("--date-to", required=True, help="終了日 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="実際には更新せず確認のみ")
    args = parser.parse_args()

    print(f"MySQL から {args.date_from}→{args.date_to} のレース名を取得中...")
    race_names = fetch_race_names(args.date_from, args.date_to)
    print(f"  {len(race_names)} 件のレース名を取得。")

    if args.dry_run:
        print("\n[DRY RUN モード] PostgreSQL への書き込みは行いません。")
    else:
        print("\nPostgreSQL を更新中...")

    fix_postgres(race_names, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
