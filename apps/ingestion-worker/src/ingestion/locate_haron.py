"""デバッグ用: RA レコード内の HaronTimeL3（レース後半3ハロン）バイト位置を特定する。

RPCI（レースPCI）は「1着馬の走破タイム」「距離」「レース後半3F」から算出するが、
レース後半3F は RA レコードの HaronTimeL3 にある。その byte 位置はまだ未確定のため、
保存済みの実 RA レコードに対して本ツールで位置を特定する（Kyori/TrackCD と同じ手順）。

前提: 先に dump_records.py を実行して raw_dump/dumped_ra.txt を保存しておく。

使い方（2通り）:
    # ① レースの全ハロンタイムを渡す（最も確実・一意特定）
    #    JRA 結果ページ「タイム → ハロンタイム」をそのまま貼り付け可（'-' や空白は無視）:
    python -m ingestion.locate_haron raw_dump/dumped_ra.txt "12.0 10.7 11.2 11.3 11.4 11.9"

    # ② レース後半3F の秒数だけを渡す（候補を絞り込み）
    python -m ingestion.locate_haron raw_dump/dumped_ra.txt 34.6

出力されるのはバイト **オフセット（数値）** と、利用者が入力したハロンタイムから
算出した分割値のみ。生レコードは表示・保存しない（生データ再配布禁止のため）。
特定したオフセットを jv_spec.RA_FIELDS に反映する。

HaronTime ブロックは [前半3F][前半4F][後半3F][後半4F] の 3桁×4 が連続する。
HaronTimeL3 は 3 番目なので、その直前6バイト・直後3バイトも数字になる点で絞り込む。
全ハロンタイム指定時は、LapTime 配列（各ハロンの並び）と HaronTime ブロックの
2 つの独立アンカーで交差検証し、一意のオフセットを返す。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

from ingestion.parser.common import to_cp932


def _d3(seconds: float) -> str:
    """秒を 1/10 秒 3 桁の ASCII（例: 34.6 → '346'）にする。"""
    return f"{round(seconds * 10):03d}"


def _is_digit_run(raw: bytes, start: int, length: int) -> bool:
    """raw[start:start+length] がすべて ASCII 数字なら True。"""
    if start < 0 or start + length > len(raw):
        return False
    return raw[start : start + length].isdigit()


class LapLocateResult(NamedTuple):
    """全ハロン指定時の HaronTimeL3 特定結果。"""

    l3_offset: int        # HaronTimeL3 開始バイト（= block_offset + 6）
    block_offset: int     # HaronTime ブロック [S3 S4 L3 L4] 開始バイト
    laps_offset: int      # LapTime 配列開始バイト（見つからなければ -1）


def haron_splits(halon_times: list[float]) -> tuple[str, str, str, str]:
    """ハロンタイム列から (S3, S4, L3, L4) を 1/10 秒 3 桁文字列で返す。

    S3=前半3F, S4=前半4F, L3=後半3F, L4=後半4F。
    """
    if len(halon_times) < 4:
        raise ValueError("ハロンタイムは最低4本（後半4F算出に必要）必要です")
    s3 = _d3(sum(halon_times[:3]))
    s4 = _d3(sum(halon_times[:4]))
    l3 = _d3(sum(halon_times[-3:]))
    l4 = _d3(sum(halon_times[-4:]))
    return s3, s4, l3, l4


def locate_haron_l3_by_laps(
    record: str, halon_times: list[float]
) -> LapLocateResult | None:
    """全ハロンタイムから HaronTimeL3 オフセットを一意特定する（最も確実）。

    2 つの独立アンカーで交差検証する:
      1. HaronTime ブロック [S3][S4][L3][L4]（3桁×4=12byte 連続）→ L3 = block + 6
      2. LapTime 配列（各ハロンの 3桁連続の並び）→ ブロックはこの後方にあるはず

    ブロックは LapTime 配列より後方にあるため、配列が見つかればその位置以降で
    ブロックを探し、コーナータイム等への誤一致を避ける。配列が見つからない場合は
    レコード全体からブロックを探してフォールバックする。
    """
    raw = to_cp932(record)
    s3, s4, l3, l4 = haron_splits(halon_times)
    block = (s3 + s4 + l3 + l4).encode("ascii")
    laps = "".join(_d3(x) for x in halon_times).encode("ascii")

    laps_pos = raw.find(laps)
    # ブロックは LapTime 配列の後方。配列が見つかればそれ以降で探す。
    block_pos = raw.find(block, laps_pos) if laps_pos != -1 else -1
    if block_pos == -1:
        block_pos = raw.find(block)  # フォールバック: レコード全体
    if block_pos == -1:
        return None
    return LapLocateResult(
        l3_offset=block_pos + 6, block_offset=block_pos, laps_offset=laps_pos
    )


def locate_haron_l3(record: str, race_l3_seconds: float | None) -> list[int]:
    """RA レコードから HaronTimeL3 の候補オフセットを返す（後半3F のみ指定時）。

    race_l3_seconds 指定時はその値（1/10秒3桁）に一致し、かつ前後が
    HaronTime ブロック（3桁×4 連続）を成す位置のみを候補とする。
    未指定時は [700:1000] 内の「3桁×4 連続数字」ブロックの3番目を候補列挙する。
    """
    raw = to_cp932(record)
    candidates: list[int] = []

    if race_l3_seconds is not None:
        target = _d3(race_l3_seconds).encode("ascii")
        pos = raw.find(target)
        while pos != -1:
            # L3 はブロック3番目: 直前6byte(S3,S4)+自身3byte+直後3byte(L4)=12byte 連続数字
            if _is_digit_run(raw, pos - 6, 12):
                candidates.append(pos)
            pos = raw.find(target, pos + 1)
        return candidates

    # フォールバック: レース後半に多い lap 領域を広めに走査し 12byte 数字ブロックを探す
    i = 700
    while i < min(len(raw), 1000):
        if _is_digit_run(raw, i, 12):
            candidates.append(i + 6)  # ブロック3番目(L3)の開始位置
            i += 12
        else:
            i += 1
    return candidates


def _parse_floats(args: list[str]) -> list[float]:
    """argv 断片から小数（ハロンタイム/秒）をすべて抽出する。

    JRA 結果ページの「12.0 - 10.7 - 11.2 - ...」をそのまま貼り付けても拾えるよう、
    数値以外（'-' や空白、シェルが分割した断片）は無視する。
    """
    text = " ".join(args)
    return [float(x) for x in re.findall(r"\d+\.\d+", text)]


def _print_usage() -> None:
    print("使い方:")
    print(
        '  全ハロン: python -m ingestion.locate_haron <dumped_ra.txt> '
        '"12.0 10.7 11.2 11.3 11.4 11.9"'
    )
    print("  後半3F : python -m ingestion.locate_haron <dumped_ra.txt> 34.6")


def _report_seconds_mode(raw: bytes, record: str, race_l3: float | None) -> None:
    """後半3F 単独（または未指定）モードの候補出力。"""
    if race_l3 is not None:
        print(f"探索対象 レース後半3F: {race_l3} 秒 → '{_d3(race_l3)}'")
    candidates = locate_haron_l3(record, race_l3)
    if not candidates:
        print("\n候補が見つかりませんでした。")
        print("- レース後半3F（JRA結果ページ『上り 3F』）が正しいか確認")
        print("- 引数なしで再実行すると [700:1000] の数字ブロックを列挙します")
        return
    print(f"\nHaronTimeL3 候補オフセット: {candidates}")
    print("--- 各候補の HaronTime ブロック [前3F 前4F 後3F 後4F] ---")
    for off in candidates:
        block = raw[off - 6 : off + 6].decode("ascii", errors="replace")
        bs3, bs4, bl3, bl4 = block[0:3], block[3:6], block[6:9], block[9:12]
        print(f"  L3@[{off}:{off + 3}]  前3F={bs3} 前4F={bs4} 後3F={bl3} 後4F={bl4}")
    print("\nこのうち妥当な候補の L3 開始オフセットを教えてください。")
    print("→ jv_spec.RA_FIELDS に HaronTimeL3 を登録して RPCI 算出を有効化します。")


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        print("先に dump_records.py を実行して raw_dump/dumped_ra.txt を保存してください。")
        sys.exit(1)

    record = path.read_text(encoding="utf-8").rstrip("\r\n")
    raw = to_cp932(record)
    print(f"RA レコード長: {len(raw)} bytes")

    floats = _parse_floats(sys.argv[2:])

    # --- 全ハロン指定（4本以上 → 一意特定モード） ---
    if len(floats) >= 4:
        s3, s4, l3, l4 = haron_splits(floats)
        print(f"ハロンタイム {len(floats)} 本 → 前3F={s3} 前4F={s4} 後3F={l3} 後4F={l4}")
        res = locate_haron_l3_by_laps(record, floats)
        if res is not None:
            off = res.l3_offset
            print(f"\n★ HaronTimeL3 オフセット = {off}（[{off}:{off + 3}]）")
            print(f"  HaronTime ブロック開始 = {res.block_offset}（[S3 S4 L3 L4]）")
            if res.laps_offset != -1:
                gap = res.block_offset - res.laps_offset
                print(f"  LapTime 配列開始       = {res.laps_offset}（間隔 {gap} byte）")
            else:
                print("  LapTime 配列は不一致（HaronTime ブロック単独で確定）")
            print(f"\n→ jv_spec.RA_FIELDS に HaronTimeL3 を offset={off}, length=3 で登録します。")
            print(f"  このオフセット {off} を教えてください（または『一致』と返信）。")
            return
        print("\nHaronTime ブロックが見つかりませんでした。後半3F 単独で再探索します…")
        _report_seconds_mode(raw, record, float(int(l3)) / 10)
        return

    # --- 後半3F 単独 or 未指定 ---
    _report_seconds_mode(raw, record, floats[0] if floats else None)


if __name__ == "__main__":
    main()
