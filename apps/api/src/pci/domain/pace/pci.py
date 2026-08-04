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

# pci-v3: レースRPCIを「個馬PCIと同じ式をレース自身へ適用」へ修正（ADR-2026-08-04）。
# 個馬PCI・PCI3の式は pci-v2 から不変。
FORMULA_VERSION = "pci-v3"


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

    TARGET公式と一致する計算式（pci-v2 から不変）:
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
    race_s3f: Furlong3Time,
    race_l3f: Furlong3Time,
) -> float:
    """前半3F / 後半3F 比から RPCI を算出する【廃止済み・pci-v2 までの式】。

        synthetic_time = S3 + L3  →  仮想1200m(6F)として射影
        RPCI = calculate_pci(S3+L3, L3, distance=1200)

    警告: この式は TARGET のレースPCI と一致しない。
        中間区間を捨てて前半3Fだけを前半代表としているため、
        中間ラップが S3 と異なる距離（1200m超）で系統的に乖離する。
        1200m戦では両者が一致する（total = S3 + L3 が成り立つため）。

        実測（2026-08-02 札幌11R 芝1800m / TARGET レースPCI=51.6）:
            LAP 12.3-11.2-11.7-12.0-12.0-11.9-11.6-11.7-11.7（計106.1、S3=35.2、L3=35.0）
            この式               → 50.6  ✗
            calculate_rpci_target → 51.6  ✓（同レースの個馬PCIもTARGETと完全一致）

        誤り2: 前半3Fを常に600m扱いする。JRAのハロンタイムは距離が200mで割り切れない
        場合だけ先頭区間が端数になる（1300m = 100m + 200m×6）ため、端数距離では
        前半3Fが実際は500m。実測1,829件で平均+17.252・区分変化97.3%と誤っていた。

        pci-v3 で calculate_rpci_target へ置き換えた（ADR-2026-08-04）。
        本関数は移行前の値を再現・比較するためだけに残す。新規に呼ばないこと。
    """
    return calculate_pci(
        race_time=RaceTime(race_s3f.seconds + race_l3f.seconds),
        furlong_3f=race_l3f,
        distance=Distance(1200),
    ).value


def calculate_rpci_target(
    race_time: RaceTime,
    race_l3f: Furlong3Time,
    distance: Distance,
) -> float:
    """TARGET のレースPCI と一致する RPCI を算出する【pci-v3 本番】。

    個馬 PCI と同じ式をレース自身へ適用するだけ:
        Ave-3F = (レース走破タイム − レース後半3F) × 600 ÷ (距離 − 600)
        RPCI   = Ave-3F ÷ レース後半3F × 100 − 50

    Args:
        race_time: レースの走破タイム（＝勝ち馬のタイム）
        race_l3f:  レースラップの後半3F（勝ち馬の上がり3Fではない）
        distance:  レース距離(m)

    旧 calculate_rpci_from_lap と違い、中間区間を落とさず前半3Fの距離も仮定しないため、
    どの距離でも TARGET と一致する。race_l3f はレースラップの後半3Fで、端数区間は
    先頭にあるため常に600mを覆う。
    """
    return calculate_pci(
        race_time=race_time,
        furlong_3f=race_l3f,
        distance=distance,
    ).value


def aggregate_rpci(
    pci_values: list[float],
    finish_positions: list[int],
    race_rpci: float | None = None,
) -> RpciResult:
    """複数馬の PCI から RPCI と PCI3 を集計する。

    Args:
        pci_values:       各馬の PCI 値（finish_positions と同順）
        finish_positions: 各馬の着順（pci_values と同順）
        race_rpci:        レース自身から算出した RPCI（calculate_rpci_target）。
                          指定時はこれを RPCI として採用する。None の場合は
                          全完走馬 PCI の平均で暫定算出する（ラップ未取得時のフォールバック）。

    Returns:
        RpciResult（rpci, pci3, formula_version, sample_size, reasons）

    Raises:
        ValueError: pci_values が空の場合
    """
    if not pci_values:
        raise ValueError("PCI 値が空です。RPCI を集計できません。")
    if len(pci_values) != len(finish_positions):
        raise ValueError("pci_values と finish_positions の長さが一致しません。")

    # reasons へ指数の実数値を入れない: そのまま UI の「算出の根拠」に出るため。
    # 数値は rpci / pci3 フィールドで返し、表示側は段階評価へ翻訳する。
    if race_rpci is not None:
        rpci = round(race_rpci, 1)
        rpci_reason = Reason(
            code="rpci_lap",
            description="レース全体のラップから、前半と後半どちらが速かったかを比べて判定しました。",
        )
    else:
        rpci = round(sum(pci_values) / len(pci_values), 1)
        rpci_reason = Reason(
            code="rpci_sample",
            description=(
                f"レースラップが未取得のため、完走した {len(pci_values)} 頭の走破内容から"
                "暫定的に判定しました。"
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
                description=(
                    f"上位3着馬 {len(top3_pcis)} 頭の走りから、"
                    "上位馬にとってどんな流れだったかを判定しました。"
                ),
            )
        )
    else:
        reasons.append(
            Reason(
                code="pci3_unavailable",
                description="上位3着馬のデータが不足しており、上位馬の傾向は判定できません。",
            )
        )

    return RpciResult(
        rpci=rpci,
        pci3=pci3,
        formula_version=FORMULA_VERSION,
        sample_size=len(pci_values),
        reasons=tuple(reasons),
    )
