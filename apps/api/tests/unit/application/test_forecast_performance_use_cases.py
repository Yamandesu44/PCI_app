"""直近予想精度サマリーのユースケーステスト。"""

from __future__ import annotations

import datetime

from pci.application.forecast_performance_use_cases import (
    GetForecastPerformanceUseCase,
)
from pci.domain.pace.mart_repository import PredictionEvaluationRecord
from tests.unit.application.fake_mart_repository import FakeMartRepository

NOW = datetime.datetime(2026, 7, 23, 0, tzinfo=datetime.UTC)


def _record(
    race_key: str,
    race_date: datetime.date,
    track_type: str,
    predicted_label: str,
    actual_rpci: float,
) -> PredictionEvaluationRecord:
    return PredictionEvaluationRecord(
        race_key=race_key,
        race_date=race_date,
        track_type=track_type,
        predicted_label=predicted_label,
        actual_rpci=actual_rpci,
        confidence=0.7,
        model_version="rule-v4",
    )


def test_summarizes_overall_and_track_type_without_internal_values() -> None:
    repo = FakeMartRepository()
    repo.prediction_evaluations = [
        _record("2026072005010101", datetime.date(2026, 7, 20), "芝", "スロー", 55.0),
        _record("2026071905010102", datetime.date(2026, 7, 19), "芝", "平均", 45.0),
        _record("2026071805010103", datetime.date(2026, 7, 18), "ダート", "平均", 43.0),
        _record("2026042405010104", datetime.date(2026, 4, 24), "芝", "ハイ", 45.0),
    ]

    output = GetForecastPerformanceUseCase(repo).execute(now=NOW)

    assert output.date_from == "2026-04-25"
    assert output.date_to == "2026-07-23"
    assert output.period_days == 90
    assert output.sample_size == 3
    assert output.hit_count == 2
    assert output.hit_rate == 0.667
    assert [(group.key, group.sample_size, group.hit_rate) for group in output.groups] == [
        ("overall", 3, 0.667),
        ("turf", 2, 0.5),
        ("dirt", 1, 1.0),
    ]
    assert "rpci" not in vars(output)
    assert all("rpci" not in vars(group) for group in output.groups)


def test_empty_period_returns_null_rate() -> None:
    output = GetForecastPerformanceUseCase(FakeMartRepository()).execute(now=NOW)

    assert output.sample_size == 0
    assert output.hit_count == 0
    assert output.hit_rate is None
    assert all(group.hit_rate is None for group in output.groups)
