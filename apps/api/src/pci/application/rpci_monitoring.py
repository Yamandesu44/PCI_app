"""ダートRPCI v4の期間外品質を判定する。

採用時の独立評価を基準に、確定レースが十分に蓄積するまでは判定を保留する。
条件を外れた場合も自動でモデルを置換せず、再学習候補の比較開始だけを促す。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pci.application.backtest import BacktestReport
from pci.domain.pace.rpci_forecast import PaceLabel

DIRT_V4_MODEL_VERSION = "lgbm-dirt-v4-lap-history"


class RpciMonitoringStatus(StrEnum):
    """RPCIモデル監視の判定状態。"""

    NO_DATA = "no_data"
    ACCUMULATING = "accumulating"
    HEALTHY = "healthy"
    RETRAINING_REVIEW = "retraining_review"
    MODEL_MISMATCH = "model_mismatch"


@dataclass(frozen=True)
class RpciMonitoringPolicy:
    """採用時評価から定めた運用上の監視条件。"""

    expected_model_version: str = DIRT_V4_MODEL_VERSION
    minimum_races: int = 100
    minimum_races_per_label: int = 20
    maximum_mae: float = 5.94
    minimum_label_accuracy: float = 0.60
    minimum_high_recall: float = 0.60
    maximum_absolute_bias: float = 4.62


DEFAULT_DIRT_V4_POLICY = RpciMonitoringPolicy()


@dataclass(frozen=True)
class RpciMonitoringCheck:
    """単一品質指標の判定結果。"""

    metric: str
    observed: float
    operator: str
    threshold: float
    passed: bool


@dataclass(frozen=True)
class RpciMonitoringResult:
    """期間外監視の集約結果。"""

    status: RpciMonitoringStatus
    model_version: str
    race_count: int
    high_race_count: int
    average_race_count: int
    slow_race_count: int
    checks: tuple[RpciMonitoringCheck, ...]
    reasons: tuple[str, ...]


def evaluate_dirt_v4_monitoring(
    report: BacktestReport | None,
    policy: RpciMonitoringPolicy = DEFAULT_DIRT_V4_POLICY,
) -> RpciMonitoringResult:
    """バックテスト結果をダートv4の運用条件と照合する。"""

    if report is None or report.rpci is None:
        return RpciMonitoringResult(
            status=RpciMonitoringStatus.NO_DATA,
            model_version="",
            race_count=0,
            high_race_count=0,
            average_race_count=0,
            slow_race_count=0,
            checks=(),
            reasons=("対象期間に評価可能な確定ダートレースがありません。",),
        )

    high_race_count = sum(
        sample.actual_label == PaceLabel.HIGH for sample in report.rpci_samples
    )
    average_race_count = sum(
        sample.actual_label == PaceLabel.AVERAGE for sample in report.rpci_samples
    )
    slow_race_count = sum(
        sample.actual_label == PaceLabel.SLOW for sample in report.rpci_samples
    )
    if report.model_version != policy.expected_model_version:
        return RpciMonitoringResult(
            status=RpciMonitoringStatus.MODEL_MISMATCH,
            model_version=report.model_version,
            race_count=report.rpci.n,
            high_race_count=high_race_count,
            average_race_count=average_race_count,
            slow_race_count=slow_race_count,
            checks=(),
            reasons=(
                "監視対象と異なるモデルが使われています。"
                f"期待={policy.expected_model_version}、実際={report.model_version or '(不明)'}",
            ),
        )

    label_counts = (
        ("ハイ", high_race_count),
        ("平均", average_race_count),
        ("スロー", slow_race_count),
    )
    insufficient_labels = tuple(
        (label, count) for label, count in label_counts if count < policy.minimum_races_per_label
    )
    if report.rpci.n < policy.minimum_races or insufficient_labels:
        reasons: list[str] = []
        if report.rpci.n < policy.minimum_races:
            reasons.append(
                f"全体レース数が判定開始条件の{policy.minimum_races}件に未達です。"
            )
        for label, _count in insufficient_labels:
            reasons.append(
                f"{label}実績レース数が判定開始条件の"
                f"{policy.minimum_races_per_label}件に未達です。"
            )
        return RpciMonitoringResult(
            status=RpciMonitoringStatus.ACCUMULATING,
            model_version=report.model_version,
            race_count=report.rpci.n,
            high_race_count=high_race_count,
            average_race_count=average_race_count,
            slow_race_count=slow_race_count,
            checks=(),
            reasons=tuple(reasons),
        )

    high_recall = report.rpci.per_label_accuracy.get(str(PaceLabel.HIGH), 0.0)
    checks = (
        RpciMonitoringCheck(
            metric="mae",
            observed=report.rpci.mae,
            operator="<=",
            threshold=policy.maximum_mae,
            passed=report.rpci.mae <= policy.maximum_mae,
        ),
        RpciMonitoringCheck(
            metric="label_accuracy",
            observed=report.rpci.label_accuracy,
            operator=">=",
            threshold=policy.minimum_label_accuracy,
            passed=report.rpci.label_accuracy >= policy.minimum_label_accuracy,
        ),
        RpciMonitoringCheck(
            metric="high_recall",
            observed=high_recall,
            operator=">=",
            threshold=policy.minimum_high_recall,
            passed=high_recall >= policy.minimum_high_recall,
        ),
        RpciMonitoringCheck(
            metric="absolute_bias",
            observed=abs(report.rpci.bias),
            operator="<=",
            threshold=policy.maximum_absolute_bias,
            passed=abs(report.rpci.bias) <= policy.maximum_absolute_bias,
        ),
    )
    failed = tuple(check.metric for check in checks if not check.passed)
    if failed:
        return RpciMonitoringResult(
            status=RpciMonitoringStatus.RETRAINING_REVIEW,
            model_version=report.model_version,
            race_count=report.rpci.n,
            high_race_count=high_race_count,
            average_race_count=average_race_count,
            slow_race_count=slow_race_count,
            checks=checks,
            reasons=(
                f"品質条件を外れた指標: {', '.join(failed)}",
                "本番モデルは自動変更せず、同一期間で再学習候補と現行モデルを比較してください。",
            ),
        )
    return RpciMonitoringResult(
        status=RpciMonitoringStatus.HEALTHY,
        model_version=report.model_version,
        race_count=report.rpci.n,
        high_race_count=high_race_count,
        average_race_count=average_race_count,
        slow_race_count=slow_race_count,
        checks=checks,
        reasons=("すべての品質条件を満たしています。",),
    )


def format_dirt_v4_monitoring(result: RpciMonitoringResult) -> str:
    """監視結果を運用者向けの日本語へ整形する。"""

    lines = [
        "ダートRPCI v4 期間外品質監視",
        f"状態: {result.status}",
        f"モデル: {result.model_version or '(データなし)'}",
        f"評価レース: {result.race_count}件 / "
        f"実績内訳: ハイ{result.high_race_count}件・平均{result.average_race_count}件・"
        f"スロー{result.slow_race_count}件",
    ]
    if result.checks:
        lines.append("品質条件:")
        for check in result.checks:
            mark = "OK" if check.passed else "NG"
            lines.append(
                f"  [{mark}] {check.metric}: {check.observed:.3f} "
                f"{check.operator} {check.threshold:.3f}"
            )
    lines.extend(f"- {reason}" for reason in result.reasons)
    return "\n".join(lines)


def dirt_v4_monitoring_to_dict(result: RpciMonitoringResult) -> dict[str, Any]:
    """監視結果をJSON保存用の辞書へ変換する。"""

    return {
        "status": str(result.status),
        "model_version": result.model_version,
        "race_count": result.race_count,
        "high_race_count": result.high_race_count,
        "average_race_count": result.average_race_count,
        "slow_race_count": result.slow_race_count,
        "checks": [
            {
                "metric": check.metric,
                "observed": check.observed,
                "operator": check.operator,
                "threshold": check.threshold,
                "passed": check.passed,
            }
            for check in result.checks
        ],
        "reasons": list(result.reasons),
    }
