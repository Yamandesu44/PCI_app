"""デバッグ用: JV-Link から各マスタ・レースレコードを1件ずつ取得して配置を表示する。

使い方 (Windows) — どちらでも可:
    py -3.12-32 src\\ingestion\\dump_records.py        # 直接実行（PYTHONPATH 不要）
    set PYTHONPATH=%CD%\\src & py -3.12-32 -m ingestion.dump_records

JV-Data 仕様の実バイト配置を確認し、パーサのオフセットを校正するための一時ツール。
"""

from __future__ import annotations

import contextlib
import datetime
import os
import sys
from pathlib import Path

# `-m` でなく直接スクリプト実行された場合でも `import ingestion.*` が解決できるよう
# src ディレクトリ（このファイルの2階層上）を sys.path に追加する。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from ingestion.client.windows_client import WindowsJvLinkClient  # noqa: E402


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


def _dump_nonblank_regions(label: str, record: str) -> None:
    """レコード全体を走査し、空白でない領域（データが入っている箇所）を列挙する。

    距離・レース名・馬場などのフィールドが想定外の位置にある場合に発見するため。
    全角空白(\\u3000) と半角空白を「空白」とみなす。
    """
    print(f"\n--- {label}: 非空白領域マップ (len={len(record)}) ---")
    blanks = {" ", "　", "\x00"}
    i = 0
    n = len(record)
    found = False
    while i < n:
        if record[i] not in blanks:
            j = i
            while j < n and record[j] not in blanks:
                j += 1
            print(f"  [{i:4d}:{j:4d}] {record[i:j]!r}")
            found = True
            i = j
        else:
            i += 1
    if not found:
        print("  (非空白領域なし — レコードがほぼ空)")


def main() -> None:
    load_dotenv()
    sid = os.environ.get("JV_LINK_SID", "")
    # 第1引数で取得日付（未指定は今日）、第2引数で RACE の JVOpen option を指定可能。
    #   py -3.12-32 src\ingestion\dump_records.py 20260621      # option=1（既定/通常）
    #   py -3.12-32 src\ingestion\dump_records.py 20260621 4    # option=4（セットアップ）
    # 通常(1)が -1（該当データなし）なら 2（今週）や 4（セットアップ）を試す。
    target_date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y%m%d")
    race_option = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(f"取得対象日付: {target_date} / RACE option: {race_option}")
    client = WindowsJvLinkClient(sid=sid)

    # DIFF マスタ（UM/KS/CH を1回の JVOpen でまとめて取得）。
    # マスタは既に取り込み済みなので、-303（サービスキー認証エラー）等で
    # 失敗しても握りつぶし、RACE ダンプへ進む。
    um_rec: str | None = None
    ks_rec: str | None = None
    ch_rec: str | None = None
    # closing() で break 時も即座に JVClose し、JV-Link セッションを放置しない。
    try:
        with contextlib.closing(client.iter_diff_records_raw()) as diff_gen:
            for rec in diff_gen:
                spec = rec[:2]
                if spec == "UM" and um_rec is None:
                    um_rec = rec
                elif spec == "KS" and ks_rec is None:
                    ks_rec = rec
                elif spec == "CH" and ch_rec is None:
                    ch_rec = rec
                if um_rec is not None and ks_rec is not None and ch_rec is not None:
                    break
    except RuntimeError as exc:
        print(f"\n(DIFF マスタ取得をスキップ: {exc} — RACE ダンプへ進みます)")

    if um_rec is not None:
        _dump("UM (競走馬マスタ)", um_rec, {
            (12, 22): "KettoNum",
            (38, 46): "BirthDate",
            (46, 64): "UmaName",
            (182, 183): "SexCD",
        })
    else:
        print("\n(UM レコードなし)")

    if ks_rec is not None:
        _dump("KS (騎手マスタ)", ks_rec, {
            (11, 16): "KisyuCode",
            (41, 58): "KisoName",
        })
    else:
        print("\n(KS レコードなし)")

    if ch_rec is not None:
        _dump("CH (調教師マスタ)", ch_rec, {
            (11, 16): "ChokyosiCode",
            (41, 58): "ChokyosiName",
        })
    else:
        print("\n(CH レコードなし)")

    # RACE データスペックを1回の JVOpen で取得し、RA と SE を分離してダンプする。
    # （別々に JVOpen すると option=1 の再取得で2回目が空になる可能性があるため）
    print("\n" + "=" * 60)
    print("RACE データ (RA/SE を1回の JVOpen で取得)")
    print("=" * 60)
    ra_count = 0
    se_count = 0
    scanned = 0
    # closing() で break 時も即座に JVClose し、JV-Link セッションを放置しない。
    try:
        with contextlib.closing(
            client.iter_race_records_raw(target_date, target_date, option=race_option)
        ) as race_gen:
            for rec in race_gen:
                scanned += 1
                spec = rec[:2]
                if spec == "RA" and ra_count < 3:
                    _dump(f"RA #{ra_count + 1}", rec, {
                        (3, 11):  "MakeDate",
                        (11, 19): "KaisaiNengappi(開催日)?",
                        (19, 21): "JyoCd?",
                        (21, 23): "Kaiji?",
                        (23, 25): "Nichiji?",
                        (25, 27): "RaceNo?",
                        (27, 28): "YoubiCd?",
                        (28, 32): "Kyori(距離)?",
                        (32, 82): "RaceName? (50chars)",
                        (82, 84): "Tosu?",
                    })
                    # 距離・レース名がどこにあるか不明なので全体の非空白領域を出す
                    _dump_nonblank_regions(f"RA #{ra_count + 1}", rec)
                    ra_count += 1
                elif spec == "SE" and se_count < 3:
                    data_kubun = rec[2:3]
                    _dump(f"SE #{se_count + 1} (DataKubun={data_kubun})", rec, {
                        (11, 19): "KaisaiNengappi(開催日)",
                        (19, 27): "Jyo/Kaiji/Nichi/RaceNo",
                        (27, 28): "Wakuban(枠)",
                        (28, 30): "Umaban(馬番)",
                        (30, 40): "KettoNum",
                        (40, 58): "Bamei(18chars)",
                        (60, 61): "SexCD",
                        (67, 72): "KisyuCode",
                        (77, 82): "ChokyosiCode",
                    })
                    # 最初の SE と確定後(DataKubun=4)は全走査して非空白領域を表示する。
                    #   - 1件目: 騎手コード/調教師コードの位置を実データで検証するため
                    #   - DataKubun=4: 着順・タイム・通過順位の位置特定のため
                    if se_count == 0 or data_kubun == "4":
                        _dump_nonblank_regions(
                            f"SE #{se_count + 1} (DataKubun={data_kubun})", rec
                        )
                    se_count += 1
                if ra_count >= 3 and se_count >= 3:
                    break
                if scanned > 2000:  # 安全装置: 2000件走査しても揃わなければ打ち切り
                    print(f"\n(警告: {scanned} 件走査、RA={ra_count} SE={se_count} で打ち切り)")
                    break
    except RuntimeError as exc:
        print(f"\n(RACE データ取得失敗: {exc})")


if __name__ == "__main__":
    main()
