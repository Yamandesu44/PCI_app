"""locate_corners（SE コーナー通過順位位置特定ツール）の単体テスト。"""

from __future__ import annotations

from ingestion.locate_corners import (
    _CORNER_HYPOTHESIS_START,
    search_corners,
    verify_corners,
)


def _make_se_record(
    corner_1: int = 5,
    corner_2: int = 5,
    corner_3: int = 4,
    corner_4: int = 2,
    offset: int = _CORNER_HYPOTHESIS_START,
    total: int = 553,
) -> bytes:
    """コーナー通過順位を仮説オフセットに埋め込んだ合成 SE レコード（CP932 bytes）。"""
    pre = b" " * offset
    corners = f"{corner_1:02d}{corner_2:02d}{corner_3:02d}{corner_4:02d}".encode("ascii")
    post = b" " * (total - offset - len(corners))
    return pre + corners + post


_CORNERS = (5, 5, 4, 2)


def test_search_finds_corners_at_hypothesis_offset() -> None:
    """仮説オフセット [531:539] にコーナーを置いた場合に検索で見つかる。"""
    raw = _make_se_record(*_CORNERS)
    candidates = search_corners(raw, _CORNERS)
    assert _CORNER_HYPOTHESIS_START in candidates


def test_search_finds_no_match_when_absent() -> None:
    """コーナーデータが存在しない場合、候補が空。"""
    raw = b" " * 553
    candidates = search_corners(raw, _CORNERS)
    assert candidates == []


def test_search_finds_alternate_offset() -> None:
    """実際のオフセットが仮説と異なる場合も正しく検出できる。"""
    alt_offset = 480
    raw = _make_se_record(*_CORNERS, offset=alt_offset)
    candidates = search_corners(raw, _CORNERS)
    assert alt_offset in candidates
    assert _CORNER_HYPOTHESIS_START not in candidates  # 仮説位置は空白


def test_verify_corners_matches_hypothesis() -> None:
    """仮説オフセットにコーナーを置いたとき verify_corners が True を返す。"""
    raw = _make_se_record(*_CORNERS)
    result = verify_corners(raw, _CORNERS)
    assert result is True


def test_verify_corners_fails_on_mismatch() -> None:
    """コーナーが別オフセットにある場合、仮説位置の verify は False を返す。"""
    raw = _make_se_record(*_CORNERS, offset=480)
    result = verify_corners(raw, _CORNERS)
    assert result is False


def test_search_finds_all_horses_corners() -> None:
    """複数馬分のレコードでそれぞれのコーナーが一致するオフセットを見つける。"""
    corners_horse1 = (1, 1, 1, 1)
    corners_horse2 = (5, 5, 4, 2)
    corners_horse3 = (8, 7, 6, 5)

    raw1 = _make_se_record(*corners_horse1)
    raw2 = _make_se_record(*corners_horse2)
    raw3 = _make_se_record(*corners_horse3)

    c1 = set(search_corners(raw1, corners_horse1))
    c2 = set(search_corners(raw2, corners_horse2))
    c3 = set(search_corners(raw3, corners_horse3))

    common = c1 & c2 & c3
    assert _CORNER_HYPOTHESIS_START in common
