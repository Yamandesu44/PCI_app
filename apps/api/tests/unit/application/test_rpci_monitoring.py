"""ダートRPCI v4の期間外品質監視テスト。"""

from pci.application.backtest import BacktestReport, RpciAccuracy, RpciSample
from pci.application.rpci_monitoring import (
    DIRT_V4_MODEL_VERSION,
    RpciMonitoringStatus,
    dirt_v4_monitoring_to_dict,
    evaluate_dirt_v4_monitoring,
    format_dirt_v4_monitoring,
)
from pci.domain.pace.rpci_forecast import PaceLabel


def _report(
    *,
    n: int = 100,
    high_n: int = 20,
    mae: float = 4.75,
    bias: float = 2.619,
    label_accuracy: float = 0.726,
    high_recall: float = 0.906,
    model_version: str = DIRT_V4_MODEL_VERSION,
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
        for i in range(n - high_n)
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
    result = evaluate_dirt_v4_monitoring(None)

    assert result.status == RpciMonitoringStatus.NO_DATA
    assert result.race_count == 0


def test_accumulates_until_total_and_high_samples_are_sufficient() -> None:
    result = evaluate_dirt_v4_monitoring(_report(n=99, high_n=19))

    assert result.status == RpciMonitoringStatus.ACCUMULATING
    assert len(result.reasons) == 2
    assert result.checks == ()


def test_healthy_when_all_quality_conditions_pass() -> None:
    result = evaluate_dirt_v4_monitoring(_report())

    assert result.status == RpciMonitoringStatus.HEALTHY
    assert all(check.passed for check in result.checks)
    assert dirt_v4_monitoring_to_dict(result)["status"] == "healthy"
    assert "[OK] mae" in format_dirt_v4_monitoring(result)


def test_requests_retraining_review_when_any_condition_fails() -> None:
    result = evaluate_dirt_v4_monitoring(
        _report(mae=6.0, bias=4.7, label_accuracy=0.59, high_recall=0.59)
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
    result = evaluate_dirt_v4_monitoring(_report(model_version="lgbm-dirt-v1"))

    assert result.status == RpciMonitoringStatus.MODEL_MISMATCH
    assert result.checks == ()
