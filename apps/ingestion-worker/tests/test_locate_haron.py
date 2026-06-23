"""locate_haron（RA HaronTimeL3 位置特定ツール）の単体テスト。"""

from __future__ import annotations

from ingestion.locate_haron import (
    haron_splits,
    locate_haron_l3,
    locate_haron_l3_by_laps,
)

# 合成 RA レコード: offset 800 に HaronTime ブロック [前3F 前4F 後3F 後4F]
# = 34.2 / 45.2 / 34.9 / 46.5 を配置（後3F=349 が L3）。
_BLOCK_OFFSET = 800
_RECORD = (
    " " * _BLOCK_OFFSET
    + "342" + "452" + "349" + "465"
    + " " * 100
)


def test_locates_l3_by_known_agari() -> None:
    """既知のレース後半3F(34.9s)から L3 開始オフセットを特定できる。"""
    candidates = locate_haron_l3(_RECORD, 34.9)
    assert _BLOCK_OFFSET + 6 in candidates  # L3 はブロック3番目 → +6


def test_rejects_isolated_match_outside_block() -> None:
    """ブロック構造(3桁×4連続)を成さない孤立した一致は候補にしない。"""
    # '349' を数字ブロックでない場所（前後が空白）に置く
    rec = " " * 500 + "349" + " " * 500
    assert locate_haron_l3(rec, 34.9) == []


def test_fallback_lists_digit_blocks_without_agari() -> None:
    """秒数未指定時は [700:1000] の 12byte 数字ブロックの3番目を列挙する。"""
    candidates = locate_haron_l3(_RECORD, None)
    assert _BLOCK_OFFSET + 6 in candidates


# ----- 全ハロンタイムによる一意特定（locate_haron_l3_by_laps） -----

# 実データを模した合成レコード:
#   LapTime 配列(25×3=75byte) → SyogaiMileTime(4byte) → HaronTime[S3 S4 L3 L4]
# 2026-06-13 函館1R のハロンタイムを使用（前3F=33.9 前4F=45.2 後3F=34.6 後4F=45.8）。
_LAPS = [12.0, 10.7, 11.2, 11.3, 11.4, 11.9]
_LAP_OFFSET = 890
_lap_seq = "".join(f"{round(x * 10):03d}" for x in _LAPS)  # 18byte
_lap_array = _lap_seq + "000" * 19                          # 25本ぶん=75byte に padding
_syogai = "0000"                                            # SyogaiMileTime 4byte
_block = "339" + "452" + "346" + "458"                      # S3 S4 L3 L4 = 12byte
_RECORD_LAPS = (
    " " * _LAP_OFFSET
    + _lap_array
    + _syogai
    + _block
    + " " * 100
)


def test_haron_splits_computes_expected() -> None:
    """ハロンタイム列から S3/S4/L3/L4 を 1/10 秒 3 桁で算出する。"""
    assert haron_splits(_LAPS) == ("339", "452", "346", "458")


def test_locate_l3_by_full_laps_unique() -> None:
    """全ハロン指定で LapTime 配列と HaronTime ブロックの両アンカーから一意特定する。"""
    res = locate_haron_l3_by_laps(_RECORD_LAPS, _LAPS)
    assert res is not None
    assert res.laps_offset == _LAP_OFFSET                 # 890
    assert res.block_offset == _LAP_OFFSET + 75 + 4       # 969（配列75 + 障害4）
    assert res.l3_offset == res.block_offset + 6          # 975（ブロック3番目）


def test_locate_by_laps_falls_back_to_block_without_lap_array() -> None:
    """LapTime 配列が無くても HaronTime ブロック単独で特定する。"""
    rec = " " * 500 + _block + " " * 200
    res = locate_haron_l3_by_laps(rec, _LAPS)
    assert res is not None
    assert res.laps_offset == -1
    assert res.l3_offset == 506  # 500 + 6


def test_locate_by_laps_prefers_block_after_lap_array() -> None:
    """同じ12桁ブロックが配列前後に在っても、配列の後方を採用する（誤一致回避）。"""
    decoy = _block  # 配列より前に置いた紛らわしい同値ブロック
    rec = " " * 100 + decoy + " " * 300 + _lap_array + _syogai + _block + " " * 50
    res = locate_haron_l3_by_laps(rec, _LAPS)
    assert res is not None
    # decoy(@100) ではなく、LapTime 配列直後のブロックを選ぶ
    assert res.block_offset > res.laps_offset
