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

        pai = round(
            min(max(100.0 - rpci_penalty - distance_penalty - track_penalty, 0.0), 100.0), 1
        )
        label = self._classify(pai)
        reasons.append(
            Reason(
                code="pai",
                description=f"PAI={pai} → 展開「{label}」（想定{forecast.label}）",
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
                description=(
                    f"脚質「{profile.running_style}」の好ペースRPCI {preferred:.0f} と "
                    f"想定RPCI {forecast.value} の差 {gap:.1f} → 減点 {penalty:.1f}"
                ),
                contribution=-round(penalty, 1),
            )
        )
        return penalty

    def _distance_penalty(
        self, profile: HorsePaceProfile, race_distance_m: int, reasons: list[Reason]
    ) -> float:
        if profile.distance_aptitude_m is None:
            reasons.append(
                Reason(code="distance_no_data", description="距離適性データなし → 減点なし")
            )
            return 0.0
        gap_m = abs(race_distance_m - profile.distance_aptitude_m)
        penalty = min((gap_m / 200.0) * self._w.distance_weight_per_200m, self._w.distance_cap)
        reasons.append(
            Reason(
                code="distance_diff",
                description=(
                    f"距離適性 {profile.distance_aptitude_m}m と本レース {race_distance_m}m の差 "
                    f"{gap_m}m → 減点 {penalty:.1f}"
                ),
                contribution=-round(penalty, 1),
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
                    description=f"道悪不安 × 馬場「{track_condition}」→ 減点 {penalty:.1f}",
                    contribution=-round(penalty, 1),
                )
            )
            return penalty
        reasons.append(Reason(code="track_ok", description="馬場不適性なし → 減点なし"))
        return 0.0

    def _classify(self, pai: float) -> FitLabel:
        if pai >= self._w.matched_threshold:
            return FitLabel.MATCHED
        if pai < self._w.unfavorable_threshold:
            return FitLabel.UNFAVORABLE
        return FitLabel.NEUTRAL


@dataclass(frozen=True)
class PaiResult:
    """PAI 算出結果。"""

    horse_no: int
    pai: float
    fit_label: FitLabel
    model_version: str
    reasons: tuple[Reason, ...]
