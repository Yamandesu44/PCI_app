"""PCI プロパティテスト（hypothesis）。

不変条件（invariants）を検証する。
式の変更でこれらの条件が崩れた場合は formula_version を上げること（ADR-0004）。
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from pci.domain.pace.pci import calculate_pci
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime

# JRA で実際に存在する距離（m）
_VALID_DISTANCES = [800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 2500, 3000, 3200]

_pace_st = st.floats(
    min_value=10.0,
    max_value=20.0,
    allow_nan=False,
    allow_infinity=False,
)


@given(
    distance_m=st.sampled_from(_VALID_DISTANCES),
    pace=_pace_st,
)
def test_even_pace_gives_pci_50(distance_m: int, pace: float) -> None:
    """均等ペース（前後1Fタイム同一）→ PCI ≈ 50（誤差 0.1 以内）。"""
    front_furlongs = (distance_m - 600) / 200.0
    front_time = front_furlongs * pace
    back_time = 3.0 * pace

    result = calculate_pci(
        race_time=RaceTime(front_time + back_time),
        furlong_3f=Furlong3Time(back_time),
        distance=Distance(distance_m),
    )
    assert result.value == pytest.approx(50.0, abs=0.1)


@given(
    distance_m=st.sampled_from(_VALID_DISTANCES),
    front_pace=_pace_st,
    back_pace=_pace_st,
)
def test_slower_front_gives_pci_above_50(
    distance_m: int, front_pace: float, back_pace: float
) -> None:
    """前半が後半より遅い（高い秒/F）→ PCI > 50（スロー）。"""
    assume(front_pace > back_pace * 1.001)  # 有意差を確保

    front_furlongs = (distance_m - 600) / 200.0
    result = calculate_pci(
        race_time=RaceTime(front_furlongs * front_pace + 3.0 * back_pace),
        furlong_3f=Furlong3Time(3.0 * back_pace),
        distance=Distance(distance_m),
    )
    assert result.value > 50.0


@given(
    distance_m=st.sampled_from(_VALID_DISTANCES),
    front_pace=_pace_st,
    back_pace=_pace_st,
)
def test_faster_front_gives_pci_below_50(
    distance_m: int, front_pace: float, back_pace: float
) -> None:
    """前半が後半より速い（低い秒/F）→ PCI < 50（ハイ）。"""
    assume(front_pace < back_pace * 0.999)  # 有意差を確保

    front_furlongs = (distance_m - 600) / 200.0
    result = calculate_pci(
        race_time=RaceTime(front_furlongs * front_pace + 3.0 * back_pace),
        furlong_3f=Furlong3Time(3.0 * back_pace),
        distance=Distance(distance_m),
    )
    assert result.value < 50.0


@given(pace=_pace_st)
def test_even_pace_pci_independent_of_distance(pace: float) -> None:
    """均等ペースでは距離によらず PCI ≈ 50。"""
    for d in _VALID_DISTANCES:
        front_furlongs = (d - 600) / 200.0
        result = calculate_pci(
            race_time=RaceTime(front_furlongs * pace + 3.0 * pace),
            furlong_3f=Furlong3Time(3.0 * pace),
            distance=Distance(d),
        )
        assert abs(result.value - 50.0) < 0.1, f"距離 {d}m・均等ペースで PCI={result.value}≠50"


@given(
    distance_m=st.sampled_from(_VALID_DISTANCES),
    base_front_pace=_pace_st,
    back_pace=_pace_st,
    delta=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_pci_monotonic_with_front_pace(
    distance_m: int, base_front_pace: float, back_pace: float, delta: float
) -> None:
    """前半が遅くなるほど（差し有利方向）PCI は単調増加する。"""
    front_furlongs = (distance_m - 600) / 200.0

    result_base = calculate_pci(
        race_time=RaceTime(front_furlongs * base_front_pace + 3.0 * back_pace),
        furlong_3f=Furlong3Time(3.0 * back_pace),
        distance=Distance(distance_m),
    )
    result_slower = calculate_pci(
        race_time=RaceTime(front_furlongs * (base_front_pace + delta) + 3.0 * back_pace),
        furlong_3f=Furlong3Time(3.0 * back_pace),
        distance=Distance(distance_m),
    )
    assert result_slower.value >= result_base.value


@given(
    distance_m=st.sampled_from(_VALID_DISTANCES),
    front_pace=_pace_st,
    back_pace=_pace_st,
)
def test_pci_result_always_has_reasons(
    distance_m: int, front_pace: float, back_pace: float
) -> None:
    """ランダムな入力でも常に reasons が含まれる（説明可能性の担保）。"""
    assume(front_pace > 0 and back_pace > 0)
    front_furlongs = (distance_m - 600) / 200.0

    result = calculate_pci(
        race_time=RaceTime(front_furlongs * front_pace + 3.0 * back_pace),
        furlong_3f=Furlong3Time(3.0 * back_pace),
        distance=Distance(distance_m),
    )
    assert len(result.reasons) > 0
