"""デバッグ用: SE レコード内のコーナー通過順位バイト位置を特定する。

SE レコード（553 byte）内のコーナー通過順位 Jyuni1c〜Jyuni4c（各 2byte）の
バイトオフセットを実データから特定するためのツール。

dump_records.py で保存した raw_dump/dumped_se_result.txt（確定後 SE）を使う。

使い方:

  # ① コーナー順位なし: 全レコードをスキャンして候補バイト一覧を表示
  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt

  # ② 既知コーナー順位を渡して一致オフセットを特定
  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt 4 4 5 4
  #                                                                 ↑ ↑ ↑ ↑
  #                                             corner_1 corner_2 corner_3 corner_4

  # ③ コーナー順位をカンマ区切りで渡す（スペース区切りと同等）
  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt 4,4,5,4

コーナー通過順位は JRA 結果ページ（Netkeiba など）の「通過順位」欄を参照。
※ 引数なしの場合、全バイト位置をスキャンして有効値（1-18）が入りうる場所を表示。
"""

from __future__ import annotations

import sys
from pathlib import Path

from ingestion.parser.common import _bs, to_cp932

_CORNER_MIN = 1
_CORNER_MAX = 18
_CORNER_HYPOTHESIS_START = 531  # 仮説: 1/2/3着馬情報 の後（SE 末尾から 22 byte 前）


def _read_record(path: Path) -> bytes:
    record = path.read_text(encoding="utf-8").rstrip("\r\n")
    return to_cp932(record)


def _decode_2byte(raw: bytes, offset: int) -> int | None:
    """2byte フィールドを数値に変換。有効範囲 [1..18] 外は None。"""
    if offset + 2 > len(raw):
        return None
    s = raw[offset : offset + 2].decode("cp932", errors="replace").strip()
    if not s.isdigit():
        return None
    n = int(s)
    return n if _CORNER_MIN <= n <= _CORNER_MAX else None


def show_hypothesis(raw: bytes) -> None:
    """仮説オフセット [531:539] の内容を表示する。"""
    print(f"\n--- SE レコード長: {len(raw)} bytes (期待値: 553) ---")
    if len(raw) < _CORNER_HYPOTHESIS_START + 8:
        print(f"  (警告: レコードが短すぎます)")
        return

    print(f"\n【仮説】コーナー通過順位 @ [{_CORNER_HYPOTHESIS_START}:{_CORNER_HYPOTHESIS_START + 8}]:")
    for i, name in enumerate(["corner_1", "corner_2", "corner_3", "corner_4"]):
        s = _CORNER_HYPOTHESIS_START + i * 2
        e = s + 2
        val = _bs(raw, s, e)
        num = _decode_2byte(raw, s)
        ok = "✓" if num is not None else "✗"
        print(f"  [{s}:{e}] = {val!r}  ({name}) {ok}")

    # 周辺バイト
    ctx_start = max(0, _CORNER_HYPOTHESIS_START - 10)
    ctx_end = min(len(raw), _CORNER_HYPOTHESIS_START + 32)
    print(f"\n--- 周辺バイト [{ctx_start}:{ctx_end}] ---")
    for pos in range(ctx_start, ctx_end, 10):
        chunk = raw[pos : pos + 10]
        decoded = chunk.decode("cp932", errors="replace")
        print(f"  [{pos:3d}:{pos + 10:3d}] {decoded!r}")


def scan_candidate_windows(raw: bytes, scan_start: int = 300) -> None:
    """全 2byte ウィンドウをスキャンして有効なコーナー値（1-18）を表示する。

    start, start+2, start+4, start+6 の 4 箇所が全て有効値（1-18）の箇所を列挙する。
    valid_positions リスト経由ではなく直接オフセットを総当たりすることで、
    隣接バイトに別の有効値があっても誤検知しない。
    """
    print(f"\n--- 全スキャン: 有効コーナー値（1-18）の 2byte ウィンドウ [{scan_start}:{len(raw)}] ---")
    print("  連続4箇所の候補（コーナー1〜4 として妥当な連続）:")
    found_any = False
    for start in range(scan_start, len(raw) - 7):
        v0 = _decode_2byte(raw, start)
        if v0 is None:
            continue
        v1 = _decode_2byte(raw, start + 2)
        if v1 is None:
            continue
        v2 = _decode_2byte(raw, start + 4)
        if v2 is None:
            continue
        v3 = _decode_2byte(raw, start + 6)
        if v3 is None:
            continue
        print(f"  [{start}:{start + 8}] => {v0},{v1},{v2},{v3}")
        found_any = True

    if not found_any:
        print("  4連続の候補なし（個別に全有効位置を表示します）:")
        for i in range(scan_start, len(raw) - 1):
            v = _decode_2byte(raw, i)
            if v is not None:
                print(f"    [{i}:{i + 2}] = {v}")


def search_corners(
    raw: bytes, corners: tuple[int, int, int, int]
) -> list[int]:
    """SE レコード全体から既知コーナー順位が連続する位置を探す。

    ゼロ埋め（"04"）とスペース埋め（" 4"）の両形式を試す。
    """
    c1, c2, c3, c4 = corners
    results: list[int] = []

    for fmt in (f"{c1:02d}", f" {c1}"), (f"{c2:02d}", f" {c2}"), \
               (f"{c3:02d}", f" {c3}"), (f"{c4:02d}", f" {c4}"):
        pass  # use below

    for z1, z2, z3, z4 in (
        (f"{c1:02d}", f"{c2:02d}", f"{c3:02d}", f"{c4:02d}"),  # ゼロ埋め "04"
        (f" {c1}", f" {c2}", f" {c3}", f" {c4}"),              # スペース埋め " 4"
    ):
        target = (z1 + z2 + z3 + z4).encode("ascii")
        pos = 0
        while pos <= len(raw) - 8:
            if raw[pos : pos + 8] == target:
                results.append(pos)
            pos += 1

    return sorted(set(results))


def verify_corners(raw: bytes, corners: tuple[int, int, int, int]) -> bool:
    """既知コーナー順位が仮説オフセットと一致するか検証する。"""
    c1, c2, c3, c4 = corners
    actual = tuple(
        _decode_2byte(raw, _CORNER_HYPOTHESIS_START + i * 2) for i in range(4)
    )
    expected = (c1, c2, c3, c4)
    match = actual == expected
    print(f"  期待値: {expected}  実際値: {actual}  → {'✓ 一致' if match else '✗ 不一致'}")
    return match


def _print_usage() -> None:
    print("使い方:")
    print("  スキャン:  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt")
    print("  検証あり:  python -m ingestion.locate_corners raw_dump/dumped_se_result.txt 4 4 5 4")


def _parse_corners(argv_rest: list[str]) -> tuple[int, int, int, int] | None:
    """argv から corner_1..4 を解析する。スペース区切りまたはカンマ区切り。"""
    # カンマ区切り: "4,4,5,4"
    for arg in argv_rest:
        if "," in arg:
            parts = arg.split(",")
            if len(parts) == 4 and all(x.strip().isdigit() for x in parts):
                c1, c2, c3, c4 = [int(x.strip()) for x in parts]
                return (c1, c2, c3, c4)

    # スペース区切り: "4 4 5 4" (shel によって分割済み)
    ints = [int(a) for a in argv_rest if a.isdigit()]
    if len(ints) >= 4:
        return (ints[0], ints[1], ints[2], ints[3])

    return None


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    # ファイルパスを先頭から収集（存在チェック）
    paths: list[Path] = []
    rest: list[str] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.exists():
            paths.append(p)
        else:
            rest.append(arg)

    if not paths:
        print("エラー: SE レコードファイルが見つかりません。")
        print("先に dump_records.py を実行して raw_dump/dumped_se_result.txt を保存してください。")
        _print_usage()
        sys.exit(1)

    corners = _parse_corners(rest)
    print(f"SE レコードファイル: {[str(p) for p in paths]}")
    raws = [_read_record(p) for p in paths]

    # ----- 単一ファイルモード -----
    if len(paths) == 1:
        raw = raws[0]
        print(f"\n=== {paths[0].name} ===")
        show_hypothesis(raw)

        if corners is not None:
            c1, c2, c3, c4 = corners
            print(f"\n【検証】コーナー順位 {c1},{c2},{c3},{c4} を探索...")
            verify_corners(raw, corners)

            candidates = search_corners(raw, corners)
            if candidates:
                print(f"\n★ 全レコード検索: オフセット候補 = {candidates}")
                for off in candidates:
                    block = raw[off : off + 8].decode("cp932", errors="replace")
                    print(f"   [{off}:{off + 8}] = {block!r}")
                if _CORNER_HYPOTHESIS_START in candidates:
                    print(
                        f"\n→ 仮説 [{_CORNER_HYPOTHESIS_START}] が一致！"
                        f" jv_spec.SE_FIELDS の offset を CONFIRMED に変更してください。"
                    )
                else:
                    best = min(candidates)
                    print(f"\n→ 仮説と異なります。実オフセット = {best} を jv_spec.SE_FIELDS に設定してください。")
            else:
                print("\n  ゼロ埋め・スペース埋めいずれでもパターンが見つかりませんでした。")
                print("  → 全スキャンで候補を探します:")
                scan_candidate_windows(raw)
        else:
            print("\n  コーナー順位（JRA 結果ページの通過順位）を引数に渡すと自動で検索します:")
            print(f"  python -m ingestion.locate_corners {paths[0]} <c1> <c2> <c3> <c4>")
            print()
            scan_candidate_windows(raw)
        return

    # ----- 複数ファイル交差検証モード -----
    print(f"\n=== 複数馬交差検証（{len(paths)} 馬） ===")
    if corners is None:
        for i, (p, raw) in enumerate(zip(paths, raws)):
            print(f"\n--- {p.name} ---")
            scan_candidate_windows(raw)
        return

    candidate_sets: list[set[int]] = []
    for p, raw in zip(paths, raws):
        c = set(search_corners(raw, corners))
        candidate_sets.append(c)
        print(f"  {p.name}: 候補 = {sorted(c)}")

    common = set.intersection(*candidate_sets) if candidate_sets else set()
    if common:
        print(f"\n★ 全馬共通オフセット: {sorted(common)}")
        if _CORNER_HYPOTHESIS_START in common:
            print(f"  → 仮説 [{_CORNER_HYPOTHESIS_START}] が全馬で一致！")
        else:
            print(f"  → 実オフセット = {min(common)}")
    else:
        print("\n共通オフセットなし。コーナー順位を確認して再実行してください。")


if __name__ == "__main__":
    main()
