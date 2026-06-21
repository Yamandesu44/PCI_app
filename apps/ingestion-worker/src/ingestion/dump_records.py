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


def _to_cp932(record: str) -> bytes:
    """JV-Link が返す Unicode 文字列を元の CP932(Shift-JIS) バイト列に戻す。

    JV-Data 仕様書のオフセットは「バイト」単位。全角=2byte/半角=1byte なので、
    Unicode 位置ではなく本バイト列の位置で切り出すと仕様書と直接対応する。
    errors='replace' で未対応文字は1バイトに化けるが、開催データの数値・コード列は
    CP932 で可逆なので結果セクションの解析には影響しない。
    """
    return record.encode("cp932", errors="replace")


def _dump_bytes(label: str, record: str, offsets: dict[tuple[int, int], str]) -> None:
    """CP932 バイト列の指定オフセットを表示する（仕様書バイト位置の検証用）。"""
    raw = _to_cp932(record)
    print(f"\n--- {label}: CP932フィールド (bytelen={len(raw)}) ---")
    for (s, e), name in sorted(offsets.items()):
        txt = "(範囲外)" if len(raw) < e else raw[s:e].decode("cp932", errors="replace")
        print(f"  [{s}:{e}] {txt!r}  ← {name}")


def _dump_byte_ruler(label: str, record: str, start: int, end: int) -> None:
    """CP932 バイト列を10バイトごとに表示する（結果セクションの位置特定用）。"""
    raw = _to_cp932(record)
    print(f"\n--- {label}: バイトルーラー [{start}:{end}] (bytelen={len(raw)}) ---")
    for pos in range(start, min(end, len(raw)), 10):
        chunk = raw[pos:pos + 10]
        print(f"  [{pos:4d}:{pos + 10:4d}] {chunk.decode('cp932', errors='replace')!r}")


def main() -> None:
    load_dotenv()
    sid = os.environ.get("JV_LINK_SID", "")
    # 第1引数で RACE の fromtime(YYYYMMDD)、第2引数で JVOpen option を指定可能。
    #   py -3.12-32 src\ingestion\dump_records.py                 # 既定: 7日前/option=1
    #   py -3.12-32 src\ingestion\dump_records.py 20260613        # fromtime=20260613
    #   py -3.12-32 src\ingestion\dump_records.py 20260613 4      # option=4（セットアップ）
    #
    # レースカード/成績は開催の数日前から配信される。fromtime を開催当日にすると
    # 前日配信のカードを取りこぼし -1（該当データなし）になるため、既定では
    # 「今日の7日前」から取得する（直近の確定済みレースも同時に拾える）。
    if len(sys.argv) > 1:
        race_from = sys.argv[1]
    else:
        race_from = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d")
    race_option = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(f"RACE fromtime: {race_from} / option: {race_option}")
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
            client.iter_race_records_raw(race_from, race_from, option=race_option)
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
                    # CP932 バイト位置で仕様書フィールドを検証する（距離=byte697 等）。
                    _dump_bytes(f"RA #{ra_count + 1}", rec, {
                        (614, 615): "GradeCD?",
                        (617, 619): "SyubetuCD?(競走種別)",
                        (697, 701): "Kyori?(距離)",
                        (705, 707): "TrackCD?(芝ダ)",
                        (819, 821): "SyussoTosu?(出走頭数)",
                        (823, 824): "TenkoCD?(天候)",
                        (824, 825): "SibaBabaCD?(芝馬場)",
                        (825, 826): "DirtBabaCD?(ダ馬場)",
                    })
                    _dump_byte_ruler(f"RA #{ra_count + 1}", rec, 690, 840)
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
                    # CP932 バイト位置で調教師/騎手コード・成績フィールドを検証する。
                    # ChokyosiCode=byte85 は実データで確定済み。他は仕様書からの推定値で、
                    # バイトルーラーと突き合わせて確定する。
                    _dump_bytes(f"SE #{se_count + 1}", rec, {
                        (85, 90): "ChokyosiCode(調教師)",
                        (236, 241): "KisyuCode?(騎手)",
                        (264, 267): "BaTaijyu?(馬体重)",
                        (274, 276): "KakuteiJyuni?(確定着順)",
                        (278, 282): "Time?(走破ﾀｲﾑ)",
                        (291, 299): "Jyuni1-4c?(通過順)",
                        (330, 333): "HaronTimeL3?(上り3F)",
                    })
                    # 結果セクション全体をバイト単位で見て位置を確定する。
                    _dump_byte_ruler(f"SE #{se_count + 1}", rec, 80, 345)
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
