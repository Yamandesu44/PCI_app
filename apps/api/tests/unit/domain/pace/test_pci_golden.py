"""PCI ゴールデンテスト。

手検証済みの (走破タイム, 上がり3F, 距離) → PCI 値で計算式を固定する（ADR-0004）。
式・係数を変更した場合は必ずこのファイルも更新し、
変更根拠をコミットメッセージに記載すること。

検証方法（pci-v2 / TARGET 公式式）:
    Ave-3F = (走破タイム - 上がり3F) × 600 ÷ (距離 - 600)
    PCI    = Ave-3F ÷ 上がり3F × 100 − 50
"""

import pytest

from pci.domain.pace.pci import (
    FORMULA_VERSION,
    aggregate_rpci,
    calculate_pci,
    calculate_rpci_from_lap,
)
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime

# ----- ゴールデンテーブル -----
# (race_time_s, agari_3f_s, distance_m, expected_pci, label)
# expected_pci は小数点第1位まで（round(x, 1) の結果）
GOLDEN_CASES = [
    # 1600m・スロー寄り
    # Ave-3F = (94.4-33.9)×600/1000 = 36.3s / 33.9s → ratio=1.0708 → PCI=57.1
    (94.4, 33.9, 1600, 57.1, "1600m・スロー"),
    # 2000m・イーブン（前後ペース完全一致 → PCI=50.0）
    # Ave-3F = (120.0-36.0)×600/1400 = 36.0s / 36.0s → ratio=1.0 → PCI=50.0
    (120.0, 36.0, 2000, 50.0, "2000m・イーブン"),
    # 2000m・スロー（上がり速い）
    # Ave-3F = (124.0-33.5)×600/1400 = 38.786s / 33.5s → ratio=1.1578 → PCI=65.8
    (124.0, 33.5, 2000, 65.8, "2000m・スロー"),
    # 2000m・ハイ（上がりが相対的に遅い）
    # Ave-3F = (118.0-38.0)×600/1400 = 34.286s / 38.0s → ratio=0.9023 → PCI=40.2
    (118.0, 38.0, 2000, 40.2, "2000m・ハイ"),
    # 1200m・ハイ（短距離・前傾ラップ）
    # Ave-3F = (70.0-36.0)×600/600 = 34.0s / 36.0s → ratio=0.9444 → PCI=44.4
    (70.0, 36.0, 1200, 44.4, "1200m・ハイ"),
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


# ----- RPCI（レースラップ由来 / TARGET 準拠） -----

# (race_s3_s, race_l3_s, expected_rpci, label)
# TARGET 公式: RPCI = S3 / L3 × 100 − 50（距離非依存の前後3F直接比）
RPCI_GOLDEN_CASES = [
    # イーブン: S3=L3 → RPCI=50.0
    (35.0, 35.0, 50.0, "イーブン"),
    # スロー: S3>L3 → RPCI>50 / 36.0/35.0=1.02857 → 52.9
    (36.0, 35.0, 52.9, "スロー"),
    # ハイ: S3<L3 → RPCI<50 / 34.0/35.0=0.97143 → 47.1
    (34.0, 35.0, 47.1, "ハイ"),
    # 函館1R(2026-06-13) 実測: S3=33.9 L3=34.6 / 33.9/34.6=0.97977 → 48.0
    (33.9, 34.6, 48.0, "函館1R実測"),
]


@pytest.mark.parametrize(
    "race_s3_s, race_l3_s, expected_rpci, label",
    RPCI_GOLDEN_CASES,
    ids=[c[-1] for c in RPCI_GOLDEN_CASES],
)
def test_rpci_from_lap_golden(
    race_s3_s: float,
    race_l3_s: float,
    expected_rpci: float,
    label: str,
) -> None:
    rpci = calculate_rpci_from_lap(
        race_s3f=Furlong3Time(race_s3_s),
        race_l3f=Furlong3Time(race_l3_s),
    )
    assert rpci == pytest.approx(expected_rpci, abs=0.05), (
        f"[{label}] RPCI mismatch: got {rpci}, expected {expected_rpci}"
    )


def test_rpci_from_lap_equals_pci_on_1200m() -> None:
    """S3/L3方式はS3+L3=仮想1200mとしてcalculate_pciを呼ぶことで式一元化を保証。"""
    s3, l3 = Furlong3Time(33.9), Furlong3Time(34.6)
    assert calculate_rpci_from_lap(s3, l3) == calculate_pci(
        race_time=RaceTime(s3.seconds + l3.seconds),
        furlong_3f=l3,
        distance=Distance(1200),
    ).value


def test_aggregate_rpci_uses_lap_value_when_provided() -> None:
    """race_rpci 指定時は平均ではなくラップ由来値を採用する。"""
    pci_values = [40.0, 45.0, 50.0]  # 平均=45.0
    finish_positions = [1, 2, 3]
    result = aggregate_rpci(pci_values, finish_positions, race_rpci=58.3)
    assert result.rpci == 58.3  # 平均45.0 ではない
    assert result.pci3 == pytest.approx(45.0)  # PCI3 は従来どおり上位3頭平均
    assert any(r.code == "rpci_lap" for r in result.reasons)


def test_aggregate_rpci_falls_back_to_average_without_lap() -> None:
    """race_rpci 未指定時は従来どおり全馬平均でフォールバックする。"""
    result = aggregate_rpci([40.0, 45.0, 50.0], [1, 2, 3])
    assert result.rpci == pytest.approx(45.0)
    assert any(r.code == "rpci_sample" for r in result.reasons)
