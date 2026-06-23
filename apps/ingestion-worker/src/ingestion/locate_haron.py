"""デバッグ用: RA レコード内の HaronTimeL3（レース後半3ハロン）バイト位置を特定する。

RPCI（レースPCI）は「1着馬の走破タイム」「距離」「レース後半3F」から算出するが、
レース後半3F は RA レコードの HaronTimeL3 にある。その byte 位置はまだ未確定のため、
保存済みの実 RA レコードに対して本ツールで位置を特定する（Kyori/TrackCD と同じ手順）。

前提: 先に dump_records.py を実行して raw_dump/dumped_ra.txt を保存しておく。

使い方:
    # JRA 公式の結果ページ等で「レースの上がり3F（後半3ハロン合計）」を読み取り、
    # その秒数を第2引数に渡す（例: 34.9 秒）。
    python -m ingestion.locate_haron raw_dump/dumped_ra.txt 34.9

出力されるのはバイト**オフセット（数値）**のみで、生レコードは表示・保存しない
（生データ再配布禁止のため）。特定したオフセットを jv_spec.RA_FIELDS に反映する。

HaronTime ブロックは [前半3F][前半4F][後半3F][後半4F] の 3桁×4 が連続する。
HaronTimeL3 は 3 番目なので、その直前6バイト・直後3バイトも数字になる点で絞り込む。
"""

from __future__ import annotations

import sys
from pathlib import Path

from ingestion.parser.common import to_cp932


def _is_digit_run(raw: bytes, start: int, length: int) -> bool:
    """raw[start:start+length] がすべて ASCII 数字なら True。"""
    if start < 0 or start + length > len(raw):
        return False
    return raw[start : start + length].isdigit()


def locate_haron_l3(record: str, race_l3_seconds: float | None) -> list[int]:
    """RA レコードから HaronTimeL3 の候補オフセットを返す。

    race_l3_seconds 指定時はその値（1/10秒3桁）に一致し、かつ前後が
    HaronTime ブロック（3桁×4 連続）を成す位置のみを候補とする。
    未指定時は [700:1000] 内の「3桁×4 連続数字」ブロックの3番目を候補列挙する。
    """
    raw = to_cp932(record)
    candidates: list[int] = []

    if race_l3_seconds is not None:
        target = f"{round(race_l3_seconds * 10):03d}".encode("ascii")
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


def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python -m ingestion.locate_haron <dumped_ra.txt> [レース後半3F秒]")
        print("  例: python -m ingestion.locate_haron raw_dump/dumped_ra.txt 34.9")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        print("先に dump_records.py を実行して raw_dump/dumped_ra.txt を保存してください。")
        sys.exit(1)

    record = path.read_text(encoding="utf-8").rstrip("\r\n")
    race_l3 = float(sys.argv[2]) if len(sys.argv) > 2 else None

    raw = to_cp932(record)
    print(f"RA レコード長: {len(raw)} bytes")
    if race_l3 is not None:
        print(f"探索対象 レース後半3F: {race_l3} 秒 → '{round(race_l3 * 10):03d}'")

    candidates = locate_haron_l3(record, race_l3)
    if not candidates:
        print("\n候補が見つかりませんでした。")
        print("- レース後半3F の値（JRA結果ページの上がり3F）を正しく渡しているか確認")
        print("- 引数なしで再実行すると [700:1000] の数字ブロックを列挙します")
        return

    print(f"\nHaronTimeL3 候補オフセット: {candidates}")
    print("--- 各候補の HaronTime ブロック [前3F 前4F 後3F 後4F] ---")
    for off in candidates:
        block_start = off - 6
        block = raw[block_start : block_start + 12].decode("ascii", errors="replace")
        s3, s4, l3, l4 = block[0:3], block[3:6], block[6:9], block[9:12]
        print(f"  L3@[{off}:{off + 3}]  前3F={s3} 前4F={s4} 後3F={l3} 後4F={l4}")
    print("\nこのうち妥当な候補の L3 開始オフセットを教えてください。")
    print("→ jv_spec.RA_FIELDS に HaronTimeL3 を登録して RPCI 算出を有効化します。")


if __name__ == "__main__":
    main()
