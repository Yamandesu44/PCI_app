"""デバッグ用: SE レコード内のコーナー通過順位バイト位置を特定する。

SE レコード（553 byte）の末尾付近にコーナー通過順位 Jyuni1c〜Jyuni4c（各 2byte）が
並んでいる。JV-Data の標準レイアウトから [531:539] が最有力候補だが、実データで
確認するためのツール。

dump_records.py で保存した raw_dump/dumped_se_result.txt（確定後 SE）を使う。
同一レースの複数馬 SE ファイルがあれば交差検証できてより確実。

使い方:

  # ① 仮説オフセット [531:539] を表示するだけ（引数なし）
  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt

  # ② 既知コーナー順位を渡して仮説オフセットを検証
  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt 5 5 4 2
  #                                                                 ↑ ↑ ↑ ↑
  #                                             corner_1 corner_2 corner_3 corner_4

  # ③ 複数馬レコードで交差検証（ファイルを空白区切りで並べ、最後に各馬のコーナーを列挙）
  python -m ingestion.locate_corners se1.txt se2.txt se3.txt 1,1,1,1 5,5,4,2 8,7,6,5

コーナー通過順位は JRA 結果ページ（Netkeiba・JRA 公式など）の
「通過順位」欄から読み取れる（例: 1-1-1-1 → corner_1=1 corner_2=1 corner_3=1 corner_4=1）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from ingestion.parser.common import _bs, to_cp932

# SE レコード末尾の候補ブロック開始（実測 553 byte のうち後 22 byte = [531:553]）
# [531:533]=Jyuni1c [533:535]=Jyuni2c [535:537]=Jyuni3c [537:539]=Jyuni4c が仮説
_CORNER_HYPOTHESIS_START = 531
_CORNER_HYPOTHESIS_END = 539

# コーナー通過順位の有効範囲（フルゲート 18 頭）
_CORNER_MIN = 1
_CORNER_MAX = 18


def _read_record(path: Path) -> bytes:
    record = path.read_text(encoding="utf-8").rstrip("\r\n")
    return to_cp932(record)


def show_hypothesis(raw: bytes) -> None:
    """仮説オフセット [531:539] の内容を表示する。"""
    print(f"\n--- SE レコード長: {len(raw)} bytes (期待値: 553) ---")
    if len(raw) < _CORNER_HYPOTHESIS_END:
        print(f"  (警告: レコードが短すぎます: {len(raw)} < {_CORNER_HYPOTHESIS_END})")
        return

    print(f"\n【仮説】コーナー通過順位 @ [{_CORNER_HYPOTHESIS_START}:{_CORNER_HYPOTHESIS_END}]:")
    for i, (s, e, name) in enumerate(
        [
            (_CORNER_HYPOTHESIS_START + 0, _CORNER_HYPOTHESIS_START + 2, "corner_1"),
            (_CORNER_HYPOTHESIS_START + 2, _CORNER_HYPOTHESIS_START + 4, "corner_2"),
            (_CORNER_HYPOTHESIS_START + 4, _CORNER_HYPOTHESIS_START + 6, "corner_3"),
            (_CORNER_HYPOTHESIS_START + 6, _CORNER_HYPOTHESIS_START + 8, "corner_4"),
        ]
    ):
        val = _bs(raw, s, e)
        num = int(val) if val.isdigit() else -1
        valid = "✓" if _CORNER_MIN <= num <= _CORNER_MAX else "✗"
        print(f"  [{s}:{e}] = {val!r}  ({name}) {valid}")

    # 周辺バイトも表示（前後 10 byte）
    ctx_start = max(0, _CORNER_HYPOTHESIS_START - 10)
    ctx_end = min(len(raw), _CORNER_HYPOTHESIS_END + 20)
    print(f"\n--- 周辺バイト [{ctx_start}:{ctx_end}] ---")
    for pos in range(ctx_start, ctx_end, 10):
        chunk = raw[pos : pos + 10]
        decoded = chunk.decode("cp932", errors="replace")
        print(f"  [{pos:3d}:{pos + 10:3d}] {decoded!r}")


def verify_corners(raw: bytes, corners: tuple[int, int, int, int]) -> bool:
    """既知コーナー順位が仮説オフセットと一致するか検証する。"""
    c1, c2, c3, c4 = corners
    expected = f"{c1:02d}{c2:02d}{c3:02d}{c4:02d}"
    actual = _bs(raw, _CORNER_HYPOTHESIS_START, _CORNER_HYPOTHESIS_END).replace(" ", "")
    actual_padded = "".join(
        _bs(raw, _CORNER_HYPOTHESIS_START + i * 2, _CORNER_HYPOTHESIS_START + (i + 1) * 2).zfill(2)
        for i in range(4)
    )
    match = actual_padded == expected
    print(f"\n  期待値: {expected}  実際値: {actual_padded}  → {'✓ 一致' if match else '✗ 不一致'}")
    return match


def search_corners(raw: bytes, corners: tuple[int, int, int, int]) -> list[int]:
    """SE レコード全体から既知コーナー順位が連続する位置を探す。

    4コーナーが 2 byte ずつ連続しているオフセットを全列挙する。
    """
    c1, c2, c3, c4 = corners
    target = (
        f"{c1:02d}".encode("ascii")
        + f"{c2:02d}".encode("ascii")
        + f"{c3:02d}".encode("ascii")
        + f"{c4:02d}".encode("ascii")
    )
    candidates: list[int] = []
    pos = 0
    while pos <= len(raw) - 8:
        if raw[pos : pos + 8] == target:
            candidates.append(pos)
        pos += 1
    return candidates


def _print_usage() -> None:
    print("使い方:")
    print("  表示のみ:  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt")
    print("  検証あり:  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt 5 5 4 2")
    print("  多馬交差:  python -m ingestion.locate_corners se1.txt se2.txt 1,1,1,1 5,5,4,2")


def main() -> None:  # noqa: PLR0912
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    # 引数解析: ファイルパスと コーナー順位 (単馬: "c1 c2 c3 c4" / 多馬: "c1,c2,c3,c4") を分離
    paths: list[Path] = []
    corners_list: list[tuple[int, int, int, int]] = []

    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.exists():
            paths.append(p)
        elif "," in arg:
            parts = arg.split(",")
            if len(parts) == 4 and all(x.isdigit() for x in parts):
                corners_list.append((int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])))
        elif arg.isdigit():
            # 後続の数値引数を 4 つ集める
            corners_list.append(tuple())  # type: ignore[arg-type]  # placeholder

    # 単馬モードで引数が "c1 c2 c3 c4" 形式（スペース区切り）の場合を処理
    int_args = [int(a) for a in sys.argv[1:] if a.isdigit()]
    if int_args and not corners_list and len(int_args) >= 4:
        corners_list = [(int_args[0], int_args[1], int_args[2], int_args[3])]

    if not paths:
        print("エラー: SE レコードファイルが見つかりません。")
        print("先に dump_records.py を実行して raw_dump/dumped_se_result.txt を保存してください。")
        _print_usage()
        sys.exit(1)

    print(f"SE レコードファイル: {[str(p) for p in paths]}")
    raws = [_read_record(p) for p in paths]

    # ----- 単一ファイルモード -----
    if len(paths) == 1:
        raw = raws[0]
        print(f"\n=== {paths[0].name} ===")
        show_hypothesis(raw)

        if corners_list:
            corners = corners_list[0]
            print(
                f"\n【検証】コーナー順位 {corners[0]},{corners[1]},{corners[2]},{corners[3]} を探索..."
            )
            # 仮説オフセットで検証
            verify_corners(raw, corners)

            # 全体検索
            candidates = search_corners(raw, corners)
            if candidates:
                print(f"\n★ 全レコード検索: オフセット候補 = {candidates}")
                if _CORNER_HYPOTHESIS_START in candidates:
                    print(
                        f"  → 仮説 [{_CORNER_HYPOTHESIS_START}] が一致しています！"
                        f" jv_spec.SE_FIELDS に登録してください。"
                    )
                else:
                    print(
                        f"  → 仮説 [{_CORNER_HYPOTHESIS_START}] には見つかりませんでした。"
                        f" 上記オフセットを確認してください。"
                    )
            else:
                print("\n  パターンが見つかりません。")
                print(
                    "  - コーナー順位が仮定通りに連続していない（空白の有無など）可能性があります。"
                )
                print(
                    "  - 全ハロン形式ではなく、コーナーごとに値が分散している可能性があります。"
                )
        else:
            print(
                "\nヒント: コーナー順位（JRA 結果ページの「通過順位」）を追加引数で渡すと"
                " 自動検証します:"
            )
            print(
                f"  python -m ingestion.locate_corners {paths[0]} <corner1> <corner2> <corner3>"
                " <corner4>"
            )
        return

    # ----- 複数ファイル交差検証モード -----
    print(f"\n=== 複数馬交差検証（{len(paths)} 馬） ===")
    if len(corners_list) != len(paths):
        print(f"警告: ファイル数({len(paths)}) とコーナー数({len(corners_list)}) が合いません。")
        for i, raw in enumerate(raws):
            print(f"\n--- {paths[i].name} ---")
            show_hypothesis(raw)
        return

    # 各馬のコーナー候補オフセットを求め、全馬に共通のオフセットを探す
    candidate_sets: list[set[int]] = []
    for raw, corners in zip(raws, corners_list):
        c = set(search_corners(raw, corners))
        candidate_sets.append(c)
        print(f"  {paths[raws.index(raw)].name}: 候補 = {sorted(c)}")

    common = set.intersection(*candidate_sets) if candidate_sets else set()
    if common:
        print(f"\n★ 全馬共通オフセット: {sorted(common)}")
        if _CORNER_HYPOTHESIS_START in common:
            print(
                f"  → 仮説 [{_CORNER_HYPOTHESIS_START}] が全馬で一致！"
                f" jv_spec.SE_FIELDS を更新し、se_parser.py に反映してください。"
            )
        else:
            best = min(common)
            print(f"  → 最小オフセット {best} を確認してください。")
    else:
        print("\n全馬共通のオフセットが見つかりませんでした。")
        print("- コーナー形式が異なる可能性（2桁固定ではないかもしれません）")
        print("- 各馬のコーナー順位をもう一度確認してください")


if __name__ == "__main__":
    main()
