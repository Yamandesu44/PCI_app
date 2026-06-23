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

FORMULA_VERSION = "pci-v2"


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

    TARGET公式と一致する計算式（pci-v2）:
        Ave-3F   = (走破タイム - 上がり3F) × 600 ÷ (距離 - 600)
        PCI      = Ave-3F ÷ 上がり3F × 100 − 50

    備考: pci-v1 は ratio × 50 を使用していたが、TARGET の式は
          ratio × 100 − 50 (ratio = Ave-3F / 上がり3F) であるため修正。
          均等ペースで PCI=50 の基準は変わらないが、50 からの乖離幅が
          v1 の 2 倍になる（TARGET 値と一致するスケール）。

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
    ratio = front_pace / back_pace  # = Ave-3F / 上がり3F
    pci = round(ratio * 100.0 - 50.0, 1)

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


def calculate_rpci_from_lap(
    winner_time: RaceTime,
    race_furlong_3f: Furlong3Time,
    distance: Distance,
) -> float:
    """レースラップから RPCI（レースPCI）を算出する（TARGET 準拠）。

    RPCI は PCI と**同一の計算式**を、個別馬ではなく「レース代表値」へ適用した値:
        winner_time      = 1着馬の走破タイム（= レース走破タイム）
        race_furlong_3f  = レースラップの後半3ハロン（RA レコードの HaronTimeL3）
        distance         = レース距離

    PCI 式は calculate_pci に一元化されているため（ADR-0004）、それを再利用する。
    全出走馬 PCI の単純平均（aggregate_rpci の暫定値）とは異なり、TARGET の RPCI と
    一致する。レース後半3Fが取得できない場合は呼び出し側で平均にフォールバックする。
    """
    return calculate_pci(winner_time, race_furlong_3f, distance).value


def aggregate_rpci(
    pci_values: list[float],
    finish_positions: list[int],
    race_rpci: float | None = None,
) -> RpciResult:
    """複数馬の PCI から RPCI と PCI3 を集計する。

    Args:
        pci_values:       各馬の PCI 値（finish_positions と同順）
        finish_positions: 各馬の着順（pci_values と同順）
        race_rpci:        レースラップ由来の RPCI（TARGET 準拠）。指定時はこれを
                          RPCI として採用する。None の場合は全完走馬 PCI の平均で
                          暫定算出する（レースラップ未取得時のフォールバック）。

    Returns:
        RpciResult（rpci, pci3, formula_version, sample_size, reasons）

    Raises:
        ValueError: pci_values が空の場合
    """
    if not pci_values:
        raise ValueError("PCI 値が空です。RPCI を集計できません。")
    if len(pci_values) != len(finish_positions):
        raise ValueError("pci_values と finish_positions の長さが一致しません。")

    if race_rpci is not None:
        rpci = round(race_rpci, 1)
        rpci_reason = Reason(
            code="rpci_lap",
            description=f"レースラップ後半3Fから算出（TARGET準拠）→ RPCI={rpci}",
        )
    else:
        rpci = round(sum(pci_values) / len(pci_values), 1)
        rpci_reason = Reason(
            code="rpci_sample",
            description=(
                f"全完走馬 {len(pci_values)} 頭の PCI 平均 → RPCI={rpci}"
                "（暫定: レースラップ未取得）"
            ),
        )

    top3_pcis = [
        pci for pci, pos in zip(pci_values, finish_positions, strict=True) if pos in (1, 2, 3)
    ]
    pci3: float | None = round(sum(top3_pcis) / len(top3_pcis), 1) if top3_pcis else None

    reasons: list[Reason] = [rpci_reason]
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
