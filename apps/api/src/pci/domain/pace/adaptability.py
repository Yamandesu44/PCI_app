"""PAI (Pace Adaptability Index) 算出モジュール。

想定RPCI に対する各馬の展開適性を 0〜100 で表す独自指標（ドメインの王冠）。
本プロダクトの最重要価値「PCI を理解していない競馬ファンでも展開予想を活用できる」を
体現する説明可能な指標として、減点内訳を必ず reasons に出力する。

算出式（C10・重みは設定ファイルで調整可能）:
    PAI = 100 − RPCI差補正 − 距離補正 − 馬場補正
      RPCI差補正: 馬の好ペース（脚質由来の preferred RPCI）と想定RPCI の乖離に対する減点
      距離補正  : 距離適性の乖離に対する減点
      馬場補正  : 馬場（道悪）不適性に対する減点

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

MODEL_VERSION = "pai-v1"

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

    # 脚質ごとの「好ペース」= preferred RPCI（馬がもっとも力を出せる想定ペース）
    preferred_escape: float = 55.0
    preferred_front: float = 53.0
    preferred_flexible: float = 50.0
    preferred_stalker: float = 47.0
    preferred_closer: float = 45.0
    # 減点係数
    rpci_diff_weight: float = 5.0
    rpci_diff_cap: float = 60.0
    distance_weight_per_200m: float = 5.0
    distance_cap: float = 20.0
    off_track_penalty: float = 15.0
    # 合致ラベル閾値
    matched_threshold: float = 70.0
    unfavorable_threshold: float = 46.0


DEFAULT_WEIGHTS = PaiWeights()


class PaceAdaptabilityScorer:
    """PAI 算出器（pai-v1）。減点内訳を reasons として出力する。"""

    def __init__(self, weights: PaiWeights | None = None) -> None:
        self._w = weights or DEFAULT_WEIGHTS

    def score(
        self,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        race_distance_m: int,
        track_condition: str | None = None,
    ) -> PaiResult:
        reasons: list[Reason] = []

        rpci_penalty = self._rpci_diff_penalty(profile, forecast, reasons)
        distance_penalty = self._distance_penalty(profile, race_distance_m, reasons)
        track_penalty = self._track_penalty(profile, track_condition, reasons)

        base_pai = round(
            min(max(100.0 - rpci_penalty - distance_penalty - track_penalty, 0.0), 100.0), 1
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

    def _preferred_rpci(self, style: RunningStyleLabel) -> float:
        w = self._w
        return {
            RunningStyleLabel.ESCAPE: w.preferred_escape,
            RunningStyleLabel.FRONT: w.preferred_front,
            RunningStyleLabel.FLEXIBLE: w.preferred_flexible,
            RunningStyleLabel.STALKER: w.preferred_stalker,
            RunningStyleLabel.CLOSER: w.preferred_closer,
        }[style]

    def _rpci_diff_penalty(
        self, profile: HorsePaceProfile, forecast: RpciForecast, reasons: list[Reason]
    ) -> float:
        preferred = self._preferred_rpci(profile.running_style)
        gap = abs(forecast.value - preferred)
        penalty = min(gap * self._w.rpci_diff_weight, self._w.rpci_diff_cap)
        reasons.append(
            Reason(
                code="rpci_diff",
                description=_style_reason(profile.running_style, penalty),
            )
        )
        return penalty

    def _distance_penalty(
        self, profile: HorsePaceProfile, race_distance_m: int, reasons: list[Reason]
    ) -> float:
        if profile.distance_aptitude_m is None:
            reasons.append(
                Reason(code="distance_no_data", description="距離面は大きな不安材料を見ていません。")
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
        reasons.append(Reason(code="track_ok", description="馬場面は大きな不安材料を見ていません。"))
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
