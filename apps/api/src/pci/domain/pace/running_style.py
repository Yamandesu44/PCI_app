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
