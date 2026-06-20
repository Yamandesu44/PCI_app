"""デバッグ用: JV-Link から各マスタ・レースレコードを1件ずつ取得して配置を表示する。

使い方 (Windows):
    set PYTHONPATH=...\apps\ingestion-worker\src
    py -3.12-32 -m ingestion.dump_records

JV-Data 仕様の実バイト配置を確認し、パーサのオフセットを校正するための一時ツール。
"""

from __future__ import annotations

import datetime
import os

from dotenv import load_dotenv

from ingestion.client.windows_client import WindowsJvLinkClient


def _dump(label: str, record: str, highlight: dict[tuple[int, int], str] | None = None) -> None:
    print(f"\n===== {label} (len={len(record)}) =====")
    print("repr:", repr(record[:300]))
    print("--- 10文字ごとの位置ルーラー ---")
    for pos in range(0, min(len(record), 250), 10):
        print(f"  [{pos:3d}:{pos + 10:3d}] {record[pos:pos + 10]!r}")
    if highlight:
        print("\n--- フィールド候補 ---")
        for (s, e), label_str in sorted(highlight.items()):
            val = record[s:e] if len(record) >= e else "(範囲外)"
            print(f"  [{s}:{e}] {val!r}  ← {label_str}")


def main() -> None:
    load_dotenv()
    sid = os.environ.get("JV_LINK_SID", "")
    today = datetime.date.today().strftime("%Y%m%d")
    client = WindowsJvLinkClient(sid=sid)

    # UM
    for rec in client.iter_um_records():
        _dump("UM (競走馬マスタ)", rec, {
            (12, 22): "KettoNum",
            (38, 46): "BirthDate",
            (46, 64): "UmaName",
            (182, 183): "SexCD",
        })
        break

    # KS
    for rec in client.iter_ks_records():
        _dump("KS (騎手マスタ)", rec, {
            (11, 16): "KisyuCode",
            (41, 58): "KisoName",
        })
        break

    # CH
    for rec in client.iter_ch_records():
        _dump("CH (調教師マスタ)", rec, {
            (11, 16): "ChokyosiCode",
            (41, 58): "ChokyosiName",
        })
        break

    # RA (レース詳細) — 最初の3件を表示してフォーマットを確認する
    print("\n" + "=" * 60)
    print("RA レコード (最初の3件)")
    print("=" * 60)
    count = 0
    for rec in client.iter_ra_records(today, today):
        _dump(f"RA #{count + 1}", rec, {
            (3, 11):  "MakeDate",
            (11, 19): "KaisaiNengappi(race date)?",
            (19, 21): "JyoCd?",
            (21, 23): "Kaiji?",
            (23, 25): "Nichiji?",
            (25, 27): "RaceNo?",
            (27, 28): "YoubiCd?",
            (28, 32): "??? (0000/0074 pattern)",
            (32, 57): "RaceName? (25chars=25全角)",
            (32, 82): "RaceName? (50chars)",
            (82, 84): "Tosu?",
            (84, 88): "Kyori? or next field?",
        })
        count += 1
        if count >= 3:
            break

    # SE (馬毎レース情報) — 最初の3件を表示して race_key 構成を確認する
    print("\n" + "=" * 60)
    print("SE レコード (最初の3件) — MakeDate[3:11] が開催日か作成日かを確認")
    print("=" * 60)
    count = 0
    for rec in client.iter_se_records(today, today):
        _dump(f"SE #{count + 1}", rec, {
            (3, 11):  "MakeDate or KaisaiDate?",
            (11, 13): "JyoCd?",
            (13, 15): "Kaiji?",
            (15, 17): "Nichiji?",
            (17, 19): "RaceNo?",
            (19, 21): "Umaban?",
            (23, 33): "KettoNum?",
            (33, 69): "UmaName?",
        })
        count += 1
        if count >= 3:
            break


if __name__ == "__main__":
    main()
