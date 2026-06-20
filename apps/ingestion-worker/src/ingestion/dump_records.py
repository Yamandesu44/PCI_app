"""デバッグ用: JV-Link から各マスタ生レコードを1件ずつ取得して配置を表示する。

使い方 (Windows):
    set PYTHONPATH=...\apps\ingestion-worker\src
    py -3.12-32 -m ingestion.dump_records

JV-Data 仕様の実バイト配置を確認し、パーサのオフセットを校正するための一時ツール。
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from ingestion.client.windows_client import WindowsJvLinkClient


def _dump(label: str, record: str) -> None:
    print(f"\n===== {label} (len={len(record)}) =====")
    print("repr:", repr(record[:250]))
    print("--- 10文字ごとの位置ルーラー ---")
    for pos in range(0, min(len(record), 200), 10):
        print(f"  [{pos:3d}:{pos + 10:3d}] {record[pos:pos + 10]!r}")
    # sex フィールド付近を明示
    if len(record) > 155:
        print(f"\n--- sex 候補範囲 ---")
        print(f"  [155:165] {record[155:165]!r}")
        print(f"  [160:161] {record[160:161]!r}  ← sex_cd")


def main() -> None:
    load_dotenv()
    sid = os.environ.get("JV_LINK_SID", "")
    client = WindowsJvLinkClient(sid=sid)

    for rec in client.iter_um_records():
        _dump("UM (競走馬マスタ)", rec)
        break
    for rec in client.iter_ks_records():
        _dump("KS (騎手マスタ)", rec)
        break
    for rec in client.iter_ch_records():
        _dump("CH (調教師マスタ)", rec)
        break


if __name__ == "__main__":
    main()
