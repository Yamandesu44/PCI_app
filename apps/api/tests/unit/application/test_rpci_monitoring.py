"""本番ダートRPCIモデルの期間外品質監視テスト。"""

from pci.application.backtest import BacktestReport, RpciAccuracy, RpciSample
from pci.application.rpci_monitoring import (
    DIRT_MODEL_VERSION,
    RpciMonitoringStatus,
    dirt_monitoring_to_dict,
    evaluate_dirt_monitoring,
    format_dirt_monitoring,
)
from pci.domain.pace.rpci_forecast import PaceLabel


def _report(
    *,
    n: int = 100,
    high_n: int = 20,
    slow_n: int = 20,
    mae: float = 2.372,
    bias: float = 0.198,
    label_accuracy: float = 0.490,
    high_recall: float = 0.405,
    model_version: str = DIRT_MODEL_VERSION,
) -> BacktestReport:
    samples = [
        RpciSample(
            race_key=f"20260701050101{i:02d}",
            predicted=40.0,
            actual=40.0,
            predicted_label=PaceLabel.HIGH,
            actual_label=PaceLabel.HIGH,
            track_type="ダート",
        )
        for i in range(high_n)
    ]
    samples.extend(
        RpciSample(
            race_key=f"20260702050101{i:02d}",
            predicted=43.0,
            actual=43.0,
            predicted_label=PaceLabel.AVERAGE,
            actual_label=PaceLabel.AVERAGE,
            track_type="ダート",
        )
        for i in range(n - high_n - slow_n)
    )
    samples.extend(
        RpciSample(
            race_key=f"20260703050101{i:02d}",
            predicted=46.0,
            actual=46.0,
            predicted_label=PaceLabel.SLOW,
            actual_label=PaceLabel.SLOW,
            track_type="ダート",
        )
        for i in range(slow_n)
    )
    return BacktestReport(
        model_version=model_version,
        n_races=n,
        n_horses=0,
        skipped=0,
        rpci=RpciAccuracy(
            n=n,
            mae=mae,
            rmse=mae,
            bias=bias,
            label_accuracy=label_accuracy,
            per_label_accuracy={str(PaceLabel.HIGH): high_recall},
        ),
        pai=None,
        rpci_samples=samples,
    )


def test_no_report_is_no_data() -> None:
    result = evaluate_dirt_monitoring(None)

    assert result.status == RpciMonitoringStatus.NO_DATA
    assert result.race_count == 0


def test_accumulates_until_total_and_each_label_samples_are_sufficient() -> None:
    result = evaluate_dirt_monitoring(_report(n=99, high_n=19, slow_n=19))

    assert result.status == RpciMonitoringStatus.ACCUMULATING
    assert len(result.reasons) == 3
    assert result.checks == ()


def test_accumulates_when_slow_samples_are_insufficient_despite_total_and_high() -> None:
    result = evaluate_dirt_monitoring(_report(n=100, high_n=20, slow_n=19))

    assert result.status == RpciMonitoringStatus.ACCUMULATING
    assert result.high_race_count == 20
    assert result.average_race_count == 61
    assert result.slow_race_count == 19
    assert result.reasons == ("スロー実績レース数が判定開始条件の20件に未達です。",)


def test_accumulates_when_average_samples_are_insufficient() -> None:
    result = evaluate_dirt_monitoring(_report(n=100, high_n=41, slow_n=40))

    assert result.status == RpciMonitoringStatus.ACCUMULATING
    assert result.average_race_count == 19
    assert result.reasons == ("平均実績レース数が判定開始条件の20件に未達です。",)


def test_healthy_when_all_quality_conditions_pass() -> None:
    result = evaluate_dirt_monitoring(_report())

    assert result.status == RpciMonitoringStatus.HEALTHY
    assert all(check.passed for check in result.checks)
    payload = dirt_monitoring_to_dict(result)
    assert payload["status"] == "healthy"
    assert payload["average_race_count"] == 60
    formatted = format_dirt_monitoring(result)
    assert "ハイ20件・平均60件・スロー20件" in formatted
    assert "[OK] mae" in formatted


def test_requests_retraining_review_when_any_condition_fails() -> None:
    result = evaluate_dirt_monitoring(
        _report(mae=3.0, bias=1.6, label_accuracy=0.38, high_recall=0.31)
    )

    assert result.status == RpciMonitoringStatus.RETRAINING_REVIEW
    assert {check.metric for check in result.checks if not check.passed} == {
        "mae",
        "label_accuracy",
        "high_recall",
        "absolute_bias",
    }
    assert "自動変更せず" in result.reasons[1]


def test_rejects_report_from_another_model() -> None:
    result = evaluate_dirt_monitoring(_report(model_version="lgbm-dirt-v1"))

    assert result.status == RpciMonitoringStatus.MODEL_MISMATCH
    assert result.checks == ()
