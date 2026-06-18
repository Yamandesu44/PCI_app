"""PCI (Pace Change Index) 計算モジュール。

このファイルのみが PCI / RPCI / PCI3 の計算式を保持する（ADR-0004）。
他の場所から直接計算式を書かないこと。呼び出しのみ可。
式変更時は formula_version を更新し、ゴールデンテストも必ず更新すること。

PCI の方向性（不変・ゴールデンテストで固定）:
    PCI > 50: スロー（前半が相対的に遅い / 後半速い → 差し・追込有利）
    PCI = 50: イーブンペース
    PCI < 50: ハイ（前傾ラップ → 逃げ・先行有利）
"""

from dataclasses import dataclass

from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.domain.shared.reason import Reason

FORMULA_VERSION = "pci-v1"


@dataclass(frozen=True)
class PciResult:
    """PCI 算出結果。"""

    value: float
    formula_version: str
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class RpciResult:
    """RPCI / PCI3 集計結果。"""

    rpci: float
    pci3: float | None
    formula_version: str
    sample_size: int
    reasons: tuple[Reason, ...]


def calculate_pci(
    race_time: RaceTime,
    furlong_3f: Furlong3Time,
    distance: Distance,
) -> PciResult:
    """PCI を計算して返す。

    公開情報ベースの計算式（pci-v1）:
        前半1Fタイム = (走破タイム - 上がり3F) / ((距離 - 600) / 200)
        後半1Fタイム = 上がり3F / 3
        PCI = (前半1Fタイム / 後半1Fタイム) × 50

    Args:
        race_time:  走破タイム（秒）
        furlong_3f: 上がり3ハロン（秒）
        distance:   レース距離（m）

    Returns:
        PciResult（value, formula_version, reasons）

    Raises:
        ValueError: 上がり3Fが走破タイム以上の場合
    """
    t = race_time.seconds
    a = furlong_3f.seconds
    d = distance.meters

    if a >= t:
        raise ValueError(f"上がり3F({a}秒)は走破タイム({t}秒)より短くなければなりません")

    front_furlongs = (d - 600) / 200.0
    front_time = t - a
    front_pace = front_time / front_furlongs  # 秒/F（大きいほど遅い）
    back_pace = a / 3.0  # 秒/F
    ratio = front_pace / back_pace
    pci = round(ratio * 50.0, 1)

    if pci > 50.0:
        pace_trend = "スロー"
    elif pci < 50.0:
        pace_trend = "ハイ（前傾）"
    else:
        pace_trend = "イーブン"

    return PciResult(
        value=pci,
        formula_version=FORMULA_VERSION,
        reasons=(
            Reason(
                code="front_pace",
                description=f"前半{front_furlongs:.1f}F平均 {front_pace:.3f}秒/F",
            ),
            Reason(
                code="back_pace",
                description=f"上がり3F平均 {back_pace:.3f}秒/F",
            ),
            Reason(
                code="pace_ratio",
                description=f"前後ペース比 {ratio:.4f} → {pace_trend}（PCI={pci}）",
            ),
        ),
    )


def aggregate_rpci(
    pci_values: list[float],
    finish_positions: list[int],
) -> RpciResult:
    """複数馬の PCI から RPCI と PCI3 を集計する。

    Args:
        pci_values:       各馬の PCI 値（finish_positions と同順）
        finish_positions: 各馬の着順（pci_values と同順）

    Returns:
        RpciResult（rpci, pci3, formula_version, sample_size, reasons）

    Raises:
        ValueError: pci_values が空の場合
    """
    if not pci_values:
        raise ValueError("PCI 値が空です。RPCI を集計できません。")
    if len(pci_values) != len(finish_positions):
        raise ValueError("pci_values と finish_positions の長さが一致しません。")

    rpci = round(sum(pci_values) / len(pci_values), 1)

    top3_pcis = [
        pci for pci, pos in zip(pci_values, finish_positions, strict=True) if pos in (1, 2, 3)
    ]
    pci3: float | None = round(sum(top3_pcis) / len(top3_pcis), 1) if top3_pcis else None

    reasons: list[Reason] = [
        Reason(
            code="rpci_sample",
            description=f"全完走馬 {len(pci_values)} 頭の PCI 平均 → RPCI={rpci}",
        ),
    ]
    if pci3 is not None:
        reasons.append(
            Reason(
                code="pci3_sample",
                description=f"上位3着馬 {len(top3_pcis)} 頭の PCI 平均 → PCI3={pci3}",
            )
        )
    else:
        reasons.append(
            Reason(code="pci3_unavailable", description="上位3着馬データ不足のため PCI3 算出不可")
        )

    return RpciResult(
        rpci=rpci,
        pci3=pci3,
        formula_version=FORMULA_VERSION,
        sample_size=len(pci_values),
        reasons=tuple(reasons),
    )
