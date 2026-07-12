"""脚質判定モジュール。

4角通過順位の過去履歴（最大5走）から脚質（逃/先/差/追/自在）を判定する。
閾値は RunningStyleThresholds で設定可能（C9: 将来最適化前提）。

判定ルール（model_version = "running-style-v1"、C9 暫定定義）:
    逃げ: 1〜2番手率 >= 60%
    先行: 3〜5番手率 >= 60%
    差し: 6〜9番手率 >= 60%
    追込: 10番手以降率 >= 60%
    自在: 上記いずれにも該当しない
"""

from dataclasses import dataclass
from enum import StrEnum

from pci.domain.shared.reason import Reason

MODEL_VERSION = "running-style-v1"
PREDICTION_MODEL_VERSION = "running-style-v2-distance"


class RunningStyleLabel(StrEnum):
    ESCAPE = "逃げ"
    FRONT = "先行"
    STALKER = "差し"
    CLOSER = "追込"
    FLEXIBLE = "自在"


@dataclass(frozen=True)
class RunningStyleThresholds:
    """脚質判定閾値。設定ファイルから上書き可能（C9）。"""

    escape_low: int = 1
    escape_high: int = 2
    front_low: int = 3
    front_high: int = 5
    stalker_low: int = 6
    stalker_high: int = 9
    closer_low: int = 10
    rate_threshold: float = 0.60
    lookback_races: int = 5


DEFAULT_THRESHOLDS = RunningStyleThresholds()


@dataclass(frozen=True)
class RunningStyleResult:
    """脚質判定結果。"""

    label: RunningStyleLabel
    confidence: float
    model_version: str
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class RunningStyleHistory:
    """予想対象より前の1走分の位置取りと距離。新しい順で渡す。"""

    corner_position: int
    distance_m: int


@dataclass(frozen=True)
class DistanceStyleWeights:
    """混在型の脚質予測に使う仮係数。実データ検証後の調整を前提とする。"""

    recency_decay: float = 0.15
    distance_scale_m: int = 1200
    min_distance_weight: float = 0.4
    front_distance_bonus: float = 0.2

    def __post_init__(self) -> None:
        if self.recency_decay < 0:
            raise ValueError("新しさの減衰率は0以上である必要があります")
        if self.distance_scale_m <= 0:
            raise ValueError("距離スケールは正の値である必要があります")
        if not 0 <= self.min_distance_weight <= 1:
            raise ValueError("距離の最低重みは0〜1である必要があります")
        if self.front_distance_bonus < 0:
            raise ValueError("距離補正ボーナスは0以上である必要があります")


def classify_running_style(
    recent_corner4_positions: tuple[int, ...],
    *,
    thresholds: RunningStyleThresholds | None = None,
) -> RunningStyleResult:
    """4角通過順位の履歴から脚質を判定する。

    Args:
        recent_corner4_positions: 4角通過順位のタプル（最新順）。最大5走分を使用。
        thresholds: 判定閾値。省略時は DEFAULT_THRESHOLDS を使用。

    Returns:
        RunningStyleResult（label, confidence, model_version, reasons）
    """
    th = thresholds or DEFAULT_THRESHOLDS
    positions = recent_corner4_positions[: th.lookback_races]

    if not positions:
        return RunningStyleResult(
            label=RunningStyleLabel.FLEXIBLE,
            confidence=0.0,
            model_version=MODEL_VERSION,
            reasons=(Reason(code="no_data", description="過去走の4角通過順位データなし"),),
        )

    n = len(positions)

    def _rate(low: int, high: int) -> float:
        return sum(1 for p in positions if low <= p <= high) / n

    def _rate_from(low: int) -> float:
        return sum(1 for p in positions if p >= low) / n

    escape_rate = _rate(th.escape_low, th.escape_high)
    front_rate = _rate(th.front_low, th.front_high)
    stalker_rate = _rate(th.stalker_low, th.stalker_high)
    closer_rate = _rate_from(th.closer_low)

    candidates: list[tuple[float, RunningStyleLabel, str]] = [
        (escape_rate, RunningStyleLabel.ESCAPE, "逃げ"),
        (front_rate, RunningStyleLabel.FRONT, "先行"),
        (stalker_rate, RunningStyleLabel.STALKER, "差し"),
        (closer_rate, RunningStyleLabel.CLOSER, "追込"),
    ]

    qualified = [
        (rate, label, name) for rate, label, name in candidates if rate >= th.rate_threshold
    ]

    if qualified:
        best_rate, best_label, best_name = max(qualified, key=lambda x: x[0])
        return RunningStyleResult(
            label=best_label,
            confidence=best_rate,
            model_version=MODEL_VERSION,
            reasons=(
                Reason(
                    code="corner4_rate",
                    description=(
                        f"{best_name}番手率 {best_rate:.0%}"
                        f"（過去{n}走の4角通過順位: {list(positions)}）"
                    ),
                    contribution=best_rate,
                ),
            ),
        )

    rates_str = (
        f"逃:{escape_rate:.0%} 先:{front_rate:.0%} 差:{stalker_rate:.0%} 追:{closer_rate:.0%}"
    )
    return RunningStyleResult(
        label=RunningStyleLabel.FLEXIBLE,
        confidence=0.0,
        model_version=MODEL_VERSION,
        reasons=(
            Reason(
                code="flexible",
                description=(f"いずれの脚質も閾値({th.rate_threshold:.0%})未満（{rates_str}）"),
            ),
        ),
    )


def predict_running_style_for_distance(
    histories: tuple[RunningStyleHistory, ...],
    target_distance_m: int,
    *,
    thresholds: RunningStyleThresholds | None = None,
    weights: DistanceStyleWeights | None = None,
) -> RunningStyleResult:
    """混在して「自在」になる履歴を、距離と新しさで今回向けに再判定する。

    60%閾値を満たす明確な脚質は従来判定を維持する。複数脚質が混在する場合だけ、
    対象距離に近い近走を重く投票し、先行と差しが競る場合は先行した距離帯で補正する。
    """
    th = thresholds or DEFAULT_THRESHOLDS
    config = weights or DistanceStyleWeights()
    recent = histories[: th.lookback_races]
    base = classify_running_style(
        tuple(history.corner_position for history in recent),
        thresholds=th,
    )
    if base.label != RunningStyleLabel.FLEXIBLE or not recent:
        return base

    labels = (
        RunningStyleLabel.ESCAPE,
        RunningStyleLabel.FRONT,
        RunningStyleLabel.STALKER,
        RunningStyleLabel.CLOSER,
    )
    votes = {label: 0.0 for label in labels}
    counts = {label: 0 for label in labels}
    front_distances: list[int] = []
    for index, history in enumerate(recent):
        label = _label_for_position(history.corner_position, th)
        distance_gap = abs(target_distance_m - history.distance_m)
        distance_weight = max(
            config.min_distance_weight,
            1.0 - distance_gap / config.distance_scale_m,
        )
        recency_weight = 1.0 / (1.0 + index * config.recency_decay)
        votes[label] += distance_weight * recency_weight
        counts[label] += 1
        if label == RunningStyleLabel.FRONT:
            front_distances.append(history.distance_m)

    distance_reason = "対象距離に近い近走を優先"
    distance_preference: RunningStyleLabel | None = None
    if front_distances and votes[RunningStyleLabel.STALKER] > 0:
        total_vote = sum(votes.values())
        average_front_distance = sum(front_distances) / len(front_distances)
        bonus = total_vote * config.front_distance_bonus
        if average_front_distance < target_distance_m:
            votes[RunningStyleLabel.FRONT] += bonus
            distance_reason = "今回より短い距離で先行した実績を優先"
            if counts[RunningStyleLabel.FRONT] == counts[RunningStyleLabel.STALKER] and counts[
                RunningStyleLabel.FRONT
            ] == max(counts.values()):
                distance_preference = RunningStyleLabel.FRONT
        elif average_front_distance > target_distance_m:
            votes[RunningStyleLabel.STALKER] += bonus
            distance_reason = "今回より長い距離での先行歴から差し寄りに補正"
            if counts[RunningStyleLabel.FRONT] == counts[RunningStyleLabel.STALKER] and counts[
                RunningStyleLabel.FRONT
            ] == max(counts.values()):
                distance_preference = RunningStyleLabel.STALKER

    selected = distance_preference or max(labels, key=lambda label: votes[label])
    vote_total = sum(votes.values())
    confidence = votes[selected] / vote_total if vote_total > 0 else 0.0
    return RunningStyleResult(
        label=selected,
        confidence=min(0.85, confidence),
        model_version=PREDICTION_MODEL_VERSION,
        reasons=(
            Reason(
                code="mixed_style_resolved",
                description=f"脚質が混在するため{distance_reason}し、{selected}寄りと予想",
                contribution=confidence,
            ),
        ),
    )


def _label_for_position(
    position: int,
    thresholds: RunningStyleThresholds,
) -> RunningStyleLabel:
    if thresholds.escape_low <= position <= thresholds.escape_high:
        return RunningStyleLabel.ESCAPE
    if thresholds.front_low <= position <= thresholds.front_high:
        return RunningStyleLabel.FRONT
    if thresholds.stalker_low <= position <= thresholds.stalker_high:
        return RunningStyleLabel.STALKER
    return RunningStyleLabel.CLOSER
