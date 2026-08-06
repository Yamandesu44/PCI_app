"""PAI (Pace Adaptability Index) 算出モジュール。

想定RPCI に対する各馬の展開適性を 0〜100 で表す独自指標（ドメインの王冠）。
本プロダクトの最重要価値「PCI を理解していない競馬ファンでも展開予想を活用できる」を
体現する説明可能な指標として、減点内訳を必ず reasons に出力する。

算出式（pai-v3・重みは設定ファイルで調整可能）:
    deviation = clamp((想定RPCI − コース中立値) ÷ 平均帯の半幅, −1, +1)
    PAI = 50 + 感応度(脚質) × pace_swing × deviation − 距離補正 − 馬場補正
      ペース補正: コース平均からの振れに対し、脚質ごとの感応度で加減点する
      距離補正  : 距離適性の乖離に対する減点
      馬場補正  : 馬場（道悪）不適性に対する減点
    `pace_affinity`（その馬自身の過去のペース別実績）があれば最後に50%で混ぜる。

**PAI は脚質内の相対量**。50 =「今回の流れは、この脚質にとって普段どおり」で、
絶対的な強さではない。ダートの追込は常に50だが好走率は 0.47x と低い。
**脚質をまたいで馬を PAI 順に並べてはならない**（docs/DECISIONS.md ADR-2026-08-04）。

合致ラベル:
    PAI >= matched_threshold      : 合致（展開の恩恵を受ける）
    PAI <  unfavorable_threshold  : 不利（展開が向かない）
    その間                        : 中立
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pci.domain.pace.affinity import (
    HorsePaceAffinityProfile,
    affinity_label,
    level_display,
    pace_level_from_index,
)
from pci.domain.pace.rpci_forecast import RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "pai-v3"

_OFF_TRACK_CONDITIONS = ("稍重", "重", "不良")


class FitLabel(StrEnum):
    """展開合致ラベル。"""

    MATCHED = "合致"
    NEUTRAL = "中立"
    UNFAVORABLE = "不利"


@dataclass(frozen=True)
class HorsePaceProfile:
    """PAI 算出に必要な馬のプロファイル。"""

    horse_no: int
    running_style: RunningStyleLabel
    distance_aptitude_m: int | None = None
    weak_on_off_track: bool = False
    pace_affinity: HorsePaceAffinityProfile | None = None


@dataclass(frozen=True)
class PaiWeights:
    """PAI 算出の重み（C10・設定ファイルから上書き可能）。"""

    # 脚質ごとのペース感応度（pai-v3）。正=スローで有利、0=ペース依存なし。
    # 2026-08-04に21万頭で較正（`--pace-style-matrix` の「自脚質の平均に対する比」）。
    #   芝   スロー時: 逃げ1.21x 先行1.12x 自在1.13x 差し1.04x 追込0.98x
    #   ダート スロー時: 逃げ1.17x 先行1.12x 自在1.09x 差し0.94x 追込0.96x
    # 差し・追込は芝とダートで符号が揃わず（差し 1.04x 対 0.94x）、ADR-0010 が
    # 「後方脚質に一貫した有利はない」と結論した通りなので 0 とする。
    #
    # 旧 pai-v2 は preferred RPCI を絶対値（逃げ55.0〜追込45.0）で持ち、コース種別の
    # 補正が無かった。分布の異なる芝(52.0)とダート(46.5)で脚質の順序が反転し、
    # ダートでは最も好走する逃げ(1.41x)に低い値、最も走らない追込(0.47x)に高い値を
    # 与えていた（docs/DECISIONS.md ADR-2026-08-04）。
    sensitivity_escape: float = 1.0
    sensitivity_front: float = 0.65
    sensitivity_flexible: float = 0.6
    sensitivity_stalker: float = 0.0
    sensitivity_closer: float = 0.0
    # 感応度1.0の脚質が、区分境界まで振れたときの最大加点/減点（PAI点）。
    pace_swing: float = 25.0
    # 振れの中心を `neutral_rpci` から動かす量（RPCI点）。
    # `neutral_rpci` は全履歴の3分位境界の中点だが、予測RPCIの分布はそこへ揃わない。
    # 2026-06-01以降の実測では 芝 50.72（中立51.85）・ダート 46.55（中立46.50）で、
    # 感応度1.0の脚質が平均 芝−6.2点・ダート+4.3点 の底上げ/底下げを受けていた。
    # これは「脚質の定数効果をPAIへ埋め込む」pai-v2 の誤りの再現なので、0以外を
    # 入れて中心を合わせられるようにする。既定0＝現行挙動のまま（未確定のため）。
    pace_center_offset_turf: float = 0.0
    pace_center_offset_dirt: float = 0.0
    # ペースの影響が無いときの基準点。ここへ加減点を足し引きする。
    # 50 = 「今回の流れは、この脚質にとって普段どおり」。
    pace_neutral_pai: float = 50.0
    distance_weight_per_200m: float = 5.0
    distance_cap: float = 20.0
    off_track_penalty: float = 15.0
    # 合致ラベル閾値（pai-v3 のスケールに合わせて再設定）。
    # 感応度1.0の脚質が区分境界まで振れると 50±25 になるため、その中間を境界にする。
    matched_threshold: float = 65.0
    unfavorable_threshold: float = 40.0


DEFAULT_WEIGHTS = PaiWeights()


def pace_half_band(track_type: str) -> float:
    """展開3分類の「平均」帯の半幅。境界で deviation が±1になるようにする。"""
    from pci.domain.pace.rpci_forecast import DEFAULT_WEIGHTS as RW

    if track_type == "ダート":
        return (RW.dirt_slow_threshold - RW.dirt_high_threshold) / 2
    return (RW.slow_threshold - RW.high_threshold) / 2


def pace_center(track_type: str, weights: PaiWeights = DEFAULT_WEIGHTS) -> float:
    """振れの中心となる RPCI。既定は `neutral_rpci` そのもの。"""
    from pci.domain.pace.style_advantage import neutral_rpci

    offset = (
        weights.pace_center_offset_dirt
        if track_type == "ダート"
        else weights.pace_center_offset_turf
    )
    return neutral_rpci(track_type) + offset


def pace_deviation(
    forecast_rpci: float, track_type: str, weights: PaiWeights = DEFAULT_WEIGHTS
) -> float:
    """コース平均からの振れを −1〜+1 へ正規化する。

    診断側でも同じ値を再現できるよう公開する。この平均が0から離れていると、
    ペース補正が脚質どうしを相対的にずらす（＝脚質の定数効果を再び埋め込む）。
    """
    half_band = pace_half_band(track_type)
    if not half_band:
        return 0.0
    return min(max((forecast_rpci - pace_center(track_type, weights)) / half_band, -1.0), 1.0)


class PaceAdaptabilityScorer:
    """PAI 算出器（pai-v3）。加減点の内訳を reasons として出力する。"""

    def __init__(self, weights: PaiWeights | None = None) -> None:
        self._w = weights or DEFAULT_WEIGHTS

    def score(
        self,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        race_distance_m: int,
        track_condition: str | None = None,
        track_type: str = "芝",
    ) -> PaiResult:
        reasons: list[Reason] = []

        # pai-v3: ペースは加減点。基準点からの振れ幅で「普段より有利か」を表す。
        pace_bonus = self._pace_bonus(profile, forecast, track_type, reasons)
        distance_penalty = self._distance_penalty(profile, race_distance_m, reasons)
        track_penalty = self._track_penalty(profile, track_condition, reasons)

        base_pai = round(
            min(
                max(
                    self._w.pace_neutral_pai + pace_bonus - distance_penalty - track_penalty,
                    0.0,
                ),
                100.0,
            ),
            1,
        )
        pai = self._blend_pace_affinity(base_pai, profile, forecast, reasons)
        label = self._classify(pai)
        reasons.append(
            Reason(
                code="pai",
                description=f"今回の流れとの総合的な相性は「{label}」です。",
            )
        )

        return PaiResult(
            horse_no=profile.horse_no,
            pai=pai,
            fit_label=label,
            model_version=MODEL_VERSION,
            reasons=tuple(reasons),
        )

    def _sensitivity(self, style: RunningStyleLabel) -> float:
        w = self._w
        return {
            RunningStyleLabel.ESCAPE: w.sensitivity_escape,
            RunningStyleLabel.FRONT: w.sensitivity_front,
            RunningStyleLabel.FLEXIBLE: w.sensitivity_flexible,
            RunningStyleLabel.STALKER: w.sensitivity_stalker,
            RunningStyleLabel.CLOSER: w.sensitivity_closer,
        }[style]

    def _pace_bonus(
        self,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        track_type: str,
        reasons: list[Reason],
    ) -> float:
        """今回の流れが、この脚質にとって普段より追い風か向かい風かを点数にする。

        コース平均（neutral_rpci）を0とし、展開区分の境界で±1になるよう正規化する。
        絶対RPCIではなくコース相対で見るのが pai-v3 の要点。芝とダートは分布が
        異なる（52.0 対 46.5）ため、絶対値で判定すると脚質の順序が反転する。
        """
        deviation = pace_deviation(forecast.value, track_type, self._w)
        bonus = self._sensitivity(profile.running_style) * self._w.pace_swing * deviation
        reasons.append(
            Reason(
                code="pace_fit",
                description=_style_reason(profile.running_style, bonus),
            )
        )
        return bonus

    def _distance_penalty(
        self, profile: HorsePaceProfile, race_distance_m: int, reasons: list[Reason]
    ) -> float:
        if profile.distance_aptitude_m is None:
            reasons.append(
                Reason(
                    code="distance_no_data",
                    description="距離面は大きな不安材料を見ていません。",
                )
            )
            return 0.0
        gap_m = abs(race_distance_m - profile.distance_aptitude_m)
        penalty = min((gap_m / 200.0) * self._w.distance_weight_per_200m, self._w.distance_cap)
        reasons.append(
            Reason(
                code="distance_diff",
                description=_distance_reason(penalty),
            )
        )
        return penalty

    def _track_penalty(
        self, profile: HorsePaceProfile, track_condition: str | None, reasons: list[Reason]
    ) -> float:
        if profile.weak_on_off_track and track_condition in _OFF_TRACK_CONDITIONS:
            penalty = self._w.off_track_penalty
            reasons.append(
                Reason(
                    code="off_track",
                    description="馬場が渋ると力を出し切れない可能性があります。",
                )
            )
            return penalty
        reasons.append(
            Reason(code="track_ok", description="馬場面は大きな不安材料を見ていません。")
        )
        return 0.0

    def _blend_pace_affinity(
        self,
        base_pai: float,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        reasons: list[Reason],
    ) -> float:
        if profile.pace_affinity is None:
            return base_pai

        predicted_level = pace_level_from_index(forecast.value)
        pace_affinity_score = profile.pace_affinity.scores[predicted_level]
        label = affinity_label(pace_affinity_score)
        preferred = level_display(profile.pace_affinity.preferred_level)
        current = level_display(predicted_level)
        if profile.pace_affinity.is_fallback:
            description = (
                "過去好走データが少ないため脚質傾向から補完しています。"
                f"得意な流れは{preferred}寄りで、今回との相性は「{label}」です。"
            )
        elif profile.pace_affinity.preferred_level != predicted_level and label in (
            "高相性",
            "合致",
        ):
            # ピーク(preferred_level)は別レベルだが、今回のレベル自体にも
            # 隣接にじみでは届かない高スコア＝直接の好走実績がある。
            # 「ピークにしか実績がない」という誤解を避けるため、今回レベルでの
            # 実績にも言及する（さもないと同じ preferred_level を持つ馬でも
            # 今回レベルでの実際の強さが説明文に反映されない）。
            description = (
                f"過去の好走は{preferred}を中心に、今回の{current}でも好走実績があり、"
                f"相性は「{label}」です。"
            )
        else:
            description = (
                f"過去の好走は{preferred}に集まっており、"
                f"今回の{current}との相性は「{label}」です。"
            )
        reasons.append(Reason(code="pace_affinity", description=description))
        return round((base_pai * 0.5) + (pace_affinity_score * 0.5), 1)

    def _classify(self, pai: float) -> FitLabel:
        if pai >= self._w.matched_threshold:
            return FitLabel.MATCHED
        if pai < self._w.unfavorable_threshold:
            return FitLabel.UNFAVORABLE
        return FitLabel.NEUTRAL


def _style_reason(style: RunningStyleLabel, penalty: float) -> str:
    if penalty <= 10.0:
        return f"脚質「{style}」の持ち味を出しやすい流れです。"
    if penalty <= 30.0:
        return f"脚質「{style}」としては極端な不利までは見ていません。"
    return f"脚質「{style}」だけで見ると、今回は少し力を出しにくい流れです。"


def _distance_reason(penalty: float) -> str:
    if penalty <= 5.0:
        return "距離面は大きな不安材料を見ていません。"
    if penalty <= 15.0:
        return "距離面では少し注意が必要です。"
    return "距離面では適性から外れる可能性があります。"


@dataclass(frozen=True)
class PaiResult:
    """PAI 算出結果。"""

    horse_no: int
    pai: float
    fit_label: FitLabel
    model_version: str
    reasons: tuple[Reason, ...]
