"""人気・本賞金の実JV-Data位置診断テスト。"""

from __future__ import annotations

from pathlib import Path

from ingestion.diagnose_jv_result_offsets import (
    NumericCandidate,
    ResultSample,
    _reference_key,
    common_numeric_candidates,
    find_numeric_candidates,
    load_references,
    reserved_match_count,
    save_references,
    supported_numeric_candidates,
)


def _sample(
    popularity: int,
    prize: int,
    pop_offset: int = 120,
    prize_offset: int = 240,
) -> ResultSample:
    raw = bytearray(b" " * 553)
    raw[pop_offset : pop_offset + 2] = f"{popularity:02d}".encode("ascii")
    raw[prize_offset : prize_offset + 7] = f"{prize // 100:07d}".encode("ascii")
    return ResultSample(bytes(raw), 1, popularity, prize)


def test_find_numeric_candidates_distinguishes_scale() -> None:
    sample = _sample(3, 1_200_000)

    candidates = find_numeric_candidates(
        sample.raw, sample.prize_money, widths=range(1, 10), scales=(1, 100)
    )

    assert NumericCandidate(240, 7, 100, "zero") in candidates
    assert NumericCandidate(240, 7, 1, "zero") not in candidates


def test_common_candidates_keep_only_shared_offset() -> None:
    samples = [_sample(3, 1_200_000), _sample(11, 850_000), _sample(7, 3_400_000)]

    popularity = common_numeric_candidates(
        samples, field="popularity", widths=range(1, 4)
    )
    prize = common_numeric_candidates(
        samples, field="prize_money", widths=range(1, 10), scales=(1, 100)
    )

    assert NumericCandidate(120, 2, 1, "zero") in popularity
    assert NumericCandidate(240, 7, 100, "zero") in prize


def test_supported_candidates_tolerate_one_mismatched_sample() -> None:
    samples = [_sample(3, 1_200_000), _sample(11, 850_000), _sample(7, 3_400_000)]
    samples.append(_sample(5, 600_000, pop_offset=130, prize_offset=250))

    popularity = supported_numeric_candidates(
        samples, field="popularity", widths=range(1, 4), minimum_ratio=0.75
    )
    prize = supported_numeric_candidates(
        samples,
        field="prize_money",
        widths=range(1, 10),
        scales=(1, 100),
        minimum_ratio=0.75,
    )

    assert (NumericCandidate(120, 2, 1, "zero"), 3) in popularity
    assert (NumericCandidate(240, 7, 100, "zero"), 3) in prize


def test_reserved_match_count_does_not_confuse_synthetic_positions() -> None:
    samples = [_sample(3, 1_200_000), _sample(11, 850_000), _sample(7, 3_400_000)]

    assert reserved_match_count(samples, "popularity", 541, 543) == 0
    assert reserved_match_count(samples, "prize_money", 543, 552) == 0


def test_reserved_match_count_accepts_exact_expected_value() -> None:
    sample = _sample(3, 1_200_000, pop_offset=541, prize_offset=543)

    assert reserved_match_count([sample], "popularity", 541, 543) == 1
    assert reserved_match_count([sample], "prize_money", 543, 552) == 0


def test_reference_key_uses_canonical_race_code() -> None:
    row = {"RACE_CODE": "2026071802011101", "UMABAN": "3"}

    assert _reference_key(row) == ("2026071802011101", 3)


def test_reference_json_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "references.json"
    expected = {
        ("2026071802011101", 3): (1, 2, 1_200_000),
        ("2026071903010209", 11): (4, 8, 450_000),
    }

    save_references(path, expected)

    assert load_references(path) == expected
