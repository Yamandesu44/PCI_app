"""PCI ゴールデンテスト。

手検証済みの (走破タイム, 上がり3F, 距離) → PCI 値で計算式を固定する（ADR-0004）。
式・係数を変更した場合は必ずこのファイルも更新し、
変更根拠をコミットメッセージに記載すること。

検証方法:
    前半1Fタイム = (走破タイム - 上がり3F) / ((距離 - 600) / 200)
    後半1Fタイム = 上がり3F / 3
    PCI = (前半1Fタイム / 後半1Fタイム) × 50
"""

import pytest

from pci.domain.pace.pci import FORMULA_VERSION, calculate_pci
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime

# ----- ゴールデンテーブル -----
# (race_time_s, agari_3f_s, distance_m, expected_pci, label)
# expected_pci は小数点第1位まで（round(x, 1) の結果）
GOLDEN_CASES = [
    # 1600m・スロー寄り
    # 前半5F 60.5s → 12.100s/F / 後半 11.300s/F → ratio=1.0708 → PCI=53.5
    (94.4, 33.9, 1600, 53.5, "1600m・スロー"),
    # 2000m・イーブン（前後ペース完全一致 → PCI=50.0）
    # 前半7F 84.0s → 12.0s/F / 後半 12.0s/F → ratio=1.0 → PCI=50.0
    (120.0, 36.0, 2000, 50.0, "2000m・イーブン"),
    # 2000m・スロー（上がり速い）
    # 前半7F 90.5s → 12.929s/F / 後半 11.167s/F → ratio=1.1579 → PCI=57.9
    (124.0, 33.5, 2000, 57.9, "2000m・スロー"),
    # 2000m・ハイ（上がりが相対的に遅い）
    # 前半7F 80.0s → 11.429s/F / 後半 12.667s/F → ratio=0.9023 → PCI=45.1
    (118.0, 38.0, 2000, 45.1, "2000m・ハイ"),
    # 1200m・ハイ（短距離・前傾ラップ）
    # 前半3F 34.0s → 11.333s/F / 後半 12.0s/F → ratio=0.9444 → PCI=47.2
    (70.0, 36.0, 1200, 47.2, "1200m・ハイ"),
]


@pytest.mark.parametrize(
    "race_time_s, agari_3f_s, distance_m, expected_pci, label",
    GOLDEN_CASES,
    ids=[c[-1] for c in GOLDEN_CASES],
)
def test_pci_golden(
    race_time_s: float,
    agari_3f_s: float,
    distance_m: int,
    expected_pci: float,
    label: str,
) -> None:
    result = calculate_pci(
        race_time=RaceTime(race_time_s),
        furlong_3f=Furlong3Time(agari_3f_s),
        distance=Distance(distance_m),
    )
    assert result.value == pytest.approx(expected_pci, abs=0.05), (
        f"[{label}] PCI mismatch: got {result.value}, expected {expected_pci}"
    )
    assert result.formula_version == FORMULA_VERSION


def test_pci_result_contains_required_reason_codes() -> None:
    """PCI 算出結果が説明に必要な reason codes をすべて含む。"""
    result = calculate_pci(
        race_time=RaceTime(94.4),
        furlong_3f=Furlong3Time(33.9),
        distance=Distance(1600),
    )
    codes = {r.code for r in result.reasons}
    assert "front_pace" in codes
    assert "back_pace" in codes
    assert "pace_ratio" in codes


def test_pci_result_is_immutable() -> None:
    """PciResult は frozen dataclass で不変。"""
    result = calculate_pci(
        race_time=RaceTime(94.4),
        furlong_3f=Furlong3Time(33.9),
        distance=Distance(1600),
    )
    with pytest.raises((AttributeError, TypeError)):
        result.value = 99.0  # type: ignore[misc]


def test_pci_raises_when_agari_exceeds_race_time() -> None:
    """上がり3F ≥ 走破タイム の場合は ValueError。"""
    with pytest.raises(ValueError, match="走破タイム"):
        calculate_pci(
            race_time=RaceTime(94.4),
            furlong_3f=Furlong3Time(100.0),
            distance=Distance(1600),
        )


def test_distance_vo_rejects_too_short() -> None:
    """距離 ≤ 600m は ValueError（PCI 計算式で前半区間がゼロになる）。"""
    with pytest.raises(ValueError):
        Distance(600)

    with pytest.raises(ValueError):
        Distance(400)


def test_distance_vo_accepts_minimum_valid() -> None:
    """800m はギリギリ有効。"""
    d = Distance(800)
    assert d.meters == 800
