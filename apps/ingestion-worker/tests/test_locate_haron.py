"""locate_haron（RA HaronTimeL3 位置特定ツール）の単体テスト。"""

from __future__ import annotations

from ingestion.locate_haron import locate_haron_l3

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
