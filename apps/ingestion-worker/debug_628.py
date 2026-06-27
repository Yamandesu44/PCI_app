"""6/28 の1頭立てバグを診断するスクリプト。

使い方:
    cd apps/ingestion-worker
    python debug_628.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

from ingestion.client.mykeibadb_client import (  # noqa: E402
    MyKeibaDbClient,
    _KAiji_COLUMNS,
    _NICHiji_COLUMNS,
    _RACE_NO_COLUMNS,
    _JYO_COLUMNS,
    _ENTRY_HORSE_NO_COLUMNS,
    _DATA_KUBUN_COLUMNS,
    _RA_TABLE_CANDIDATES,
    _SE_TABLE_CANDIDATES,
    _build_ra_record,
    _build_se_record,
    _raw_record,
    _pick,
    _str_or_none,
)
from ingestion.parser.se_parser import parse_race_key_from_se, parse_se_entry
from ingestion.parser.ra_parser import parse_ra

DATE = "20260628"
JYO_FILTER = "02"  # 函館のみ


def main() -> None:
    client = MyKeibaDbClient()
    conn = client._connect()

    ra_table = client._find_table(conn, _RA_TABLE_CANDIDATES)
    se_table = client._find_table(conn, _SE_TABLE_CANDIDATES)

    print(f"\n=== RA table: {ra_table} ===")
    print(f"=== SE table: {se_table} ===\n")

    # ---- RA の race_key を収集 ----
    ra_keys: dict[str, str] = {}  # race_key -> race_no
    print("--- RA records for 6/28 at 函館(02) ---")
    print(f"{'race_key':20s}  {'KAISAI_KAI':12s}  {'KAISAI_NICHIME':14s}  {'RACE_BANGO':10s}")

    for row in client._iter_table_by_date_range(conn, ra_table, DATE, DATE):
        if not client._row_in_date_range(row, DATE, DATE):
            continue
        jyo = _str_or_none(_pick(row, _JYO_COLUMNS)) or ""
        if jyo != JYO_FILTER:
            continue
        rec = _raw_record(row) or _build_ra_record(row)
        ra = parse_ra(rec)
        if not ra:
            continue
        kaiji_raw = _str_or_none(_pick(row, _KAiji_COLUMNS))
        nichiji_raw = _str_or_none(_pick(row, _NICHiji_COLUMNS))
        race_no_raw = _str_or_none(_pick(row, _RACE_NO_COLUMNS))
        ra_keys[ra.race_key] = race_no_raw or ""
        print(
            f"{ra.race_key:20s}  "
            f"{str(kaiji_raw):12s}  "
            f"{str(nichiji_raw):14s}  "
            f"{str(race_no_raw):10s}"
        )

    print(f"\nRA races in dict: {len(ra_keys)}")

    # ---- SE の race_key / horse_no を確認 ----
    print(f"\n--- SE records for 6/28 at 函館(02) ---")
    print(
        f"{'race_key':20s}  {'horse_no':8s}  {'kubun':6s}  "
        f"{'RACE_CODE(raw)':18s}  {'in_RA':6s}  {'entry':6s}"
    )

    match_count: dict[str, int] = {}
    skip_count = 0

    for row in client._iter_table_by_date_range(conn, se_table, DATE, DATE):
        if not client._row_in_date_range(row, DATE, DATE):
            continue
        jyo = _str_or_none(_pick(row, _JYO_COLUMNS)) or ""
        if jyo != JYO_FILTER:
            continue

        kubun_raw = _str_or_none(_pick(row, _DATA_KUBUN_COLUMNS))
        horse_no_raw = _str_or_none(_pick(row, _ENTRY_HORSE_NO_COLUMNS))
        race_code_raw = _str_or_none(_pick(row, ("RACE_CODE",)))

        rec = _raw_record(row) or _build_se_record(row)
        race_key = parse_race_key_from_se(rec)
        entry = parse_se_entry(rec)

        in_ra = race_key in ra_keys
        if in_ra:
            match_count[race_key] = match_count.get(race_key, 0) + (1 if entry else 0)
        else:
            skip_count += 1

        print(
            f"{race_key:20s}  "
            f"{str(horse_no_raw):8s}  "
            f"{str(kubun_raw):6s}  "
            f"{str(race_code_raw or ''):18s}  "
            f"{'YES' if in_ra else 'NO':6s}  "
            f"{'OK' if entry else 'None':6s}"
        )

    print(f"\n--- Summary ---")
    print(f"SE records with no matching RA: {skip_count}")
    print(f"\n{'race_key':20s}  matched_entries")
    for rk in sorted(match_count):
        print(f"{rk:20s}  {match_count[rk]}")


if __name__ == "__main__":
    main()
