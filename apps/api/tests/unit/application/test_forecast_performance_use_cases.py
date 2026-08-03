"""直近予想精度サマリーのユースケーステスト。"""

from __future__ import annotations

import datetime

import pytest

from pci.application.forecast_performance_use_cases import (
    GetForecastMissesUseCase,
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
    confidence: float = 0.7,
    confidence_method: str = "classification-margin-v1",
) -> PredictionEvaluationRecord:
    return PredictionEvaluationRecord(
        race_key=race_key,
        race_date=race_date,
        jyo_cd="05",
        distance_m=1600,
        track_type=track_type,
        race_class="テスト特別",
        predicted_label=predicted_label,
        actual_rpci=actual_rpci,
        confidence=confidence,
        model_version="rule-v4",
        confidence_method=confidence_method,
    )


def test_summarizes_overall_and_track_type_without_internal_values() -> None:
    repo = FakeMartRepository()
    repo.prediction_evaluations = [
        _record(
            "2026072005010101",
            datetime.date(2026, 7, 20),
            "芝",
            "スロー",
            55.0,
            0.72,
        ),
        _record(
            "2026071905010102",
            datetime.date(2026, 7, 19),
            "芝",
            "平均",
            45.0,
            0.55,
        ),
        _record(
            "2026071805010103",
            datetime.date(2026, 7, 18),
            "ダート",
            "平均",
            43.0,
            0.31,
        ),
        _record("2026042405010104", datetime.date(2026, 4, 24), "芝", "ハイ", 45.0),
    ]
    repo.prediction_evaluation_candidate_count = 5

    output = GetForecastPerformanceUseCase(repo).execute(now=NOW)

    assert output.date_from == "2026-04-25"
    assert output.date_to == "2026-07-23"
    assert output.period_days == 90
    assert output.eligible_race_count == 5
    assert output.sample_size == 3
    assert output.coverage_rate == 0.6
    assert output.hit_count == 2
    assert output.hit_rate == 0.667
    assert [(group.key, group.sample_size, group.hit_rate) for group in output.groups] == [
        ("overall", 3, 0.667),
        ("turf", 2, 0.5),
        ("dirt", 1, 1.0),
    ]
    assert output.previous_period.date_from == "2026-01-25"
    assert output.previous_period.date_to == "2026-04-24"
    assert [
        (group.key, group.sample_size, group.hit_rate)
        for group in output.previous_period.groups
    ] == [
        ("overall", 1, 1.0),
        ("turf", 1, 1.0),
        ("dirt", 0, None),
    ]
    assert len(output.weekly_trend) == 8
    assert output.weekly_trend[-1].date_from == "2026-07-13"
    assert output.weekly_trend[-1].date_to == "2026-07-19"
    assert output.weekly_trend[-1].sample_size == 2
    assert output.weekly_trend[-1].hit_rate == 0.5
    assert all(point.date_to < output.date_to for point in output.weekly_trend)
    assert "rpci" not in vars(output)
    assert all("rpci" not in vars(group) for group in output.groups)
    assert all("rpci" not in vars(point) for point in output.weekly_trend)
    assert [
        (group.key, group.sample_size, group.hit_rate)
        for group in output.confidence_groups
    ] == [
        ("strong", 1, 1.0),
        ("normal", 1, 0.0),
        ("caution", 1, 1.0),
    ]
    assert all("rpci" not in vars(group) for group in output.confidence_groups)
    assert [
        (group.key, group.sample_size)
        for group in output.confidence_cohort_groups
    ] == [("overall", 3), ("turf", 2), ("dirt", 1)]
    assert [
        (
            row.predicted_key,
            row.sample_size,
            [(cell.key, cell.count, cell.rate) for cell in row.cells],
        )
        for row in output.pace_matrix
    ] == [
        ("high", 0, [("high", 0, None), ("average", 0, None), ("slow", 0, None)]),
        (
            "average",
            2,
            [("high", 1, 0.5), ("average", 1, 0.5), ("slow", 0, 0.0)],
        ),
        ("slow", 1, [("high", 0, 0.0), ("average", 0, 0.0), ("slow", 1, 1.0)]),
    ]
    assert all(
        "rpci" not in vars(row)
        and all("rpci" not in vars(cell) for cell in row.cells)
        for row in output.pace_matrix
    )
    assert [
        (
            miss.race_key,
            miss.predicted_label,
            miss.actual_label,
            miss.race_class,
        )
        for miss in output.recent_misses
    ] == [
        ("2026071905010102", "平均", "ハイ", "テスト特別"),
    ]
    assert all("rpci" not in vars(miss) for miss in output.recent_misses)


def test_empty_period_returns_null_rate() -> None:
    output = GetForecastPerformanceUseCase(FakeMartRepository()).execute(now=NOW)

    assert output.sample_size == 0
    assert output.eligible_race_count == 0
    assert output.coverage_rate is None
    assert output.hit_count == 0
    assert output.hit_rate is None
    assert all(group.hit_rate is None for group in output.groups)
    assert all(
        group.hit_rate is None
        for group in output.previous_period.groups
    )
    assert all(group.hit_rate is None for group in output.confidence_groups)
    assert all(group.sample_size == 0 for group in output.confidence_cohort_groups)
    assert all(row.sample_size == 0 for row in output.pace_matrix)
    assert all(
        cell.rate is None
        for row in output.pace_matrix
        for cell in row.cells
    )
    assert len(output.weekly_trend) == 8
    assert all(point.hit_rate is None for point in output.weekly_trend)
    assert output.recent_misses == []


def test_confidence_groups_exclude_legacy_fixed_confidence() -> None:
    repo = FakeMartRepository()
    repo.prediction_evaluations = [
        _record(
            "2026072005010101",
            datetime.date(2026, 7, 20),
            "芝",
            "スロー",
            55.0,
            0.75,
            confidence_method="legacy",
        ),
        _record(
            "2026071905010102",
            datetime.date(2026, 7, 19),
            "芝",
            "平均",
            50.0,
            0.9,
        ),
    ]

    output = GetForecastPerformanceUseCase(repo).execute(now=NOW)

    assert output.sample_size == 2
    assert sum(group.sample_size for group in output.confidence_groups) == 1
    assert output.confidence_groups[0].sample_size == 1
    assert [
        (group.key, group.sample_size)
        for group in output.confidence_cohort_groups
    ] == [("overall", 1), ("turf", 1), ("dirt", 0)]


def test_recent_misses_are_limited_and_sorted_by_latest_race() -> None:
    repo = FakeMartRepository()
    repo.prediction_evaluations = [
        _record(
            f"202607{day:02d}050101{race_no:02d}",
            datetime.date(2026, 7, day),
            "芝",
            "平均",
            45.0,
        )
        for race_no, day in enumerate(range(14, 21), start=1)
    ]

    output = GetForecastPerformanceUseCase(repo).execute(now=NOW)

    assert len(output.recent_misses) == 5
    assert [miss.race_date for miss in output.recent_misses] == [
        "2026-07-20",
        "2026-07-19",
        "2026-07-18",
        "2026-07-17",
        "2026-07-16",
    ]


def test_searches_misses_with_filters_and_pagination() -> None:
    repo = FakeMartRepository()
    repo.prediction_evaluations = [
        _record(
            "2026072005010101",
            datetime.date(2026, 7, 20),
            "芝",
            "平均",
            45.0,
        ),
        _record(
            "2026071905010102",
            datetime.date(2026, 7, 19),
            "芝",
            "スロー",
            45.0,
        ),
        _record(
            "2026071805010103",
            datetime.date(2026, 7, 18),
            "ダート",
            "平均",
            47.0,
        ),
        _record(
            "2026071705010104",
            datetime.date(2026, 7, 17),
            "芝",
            "スロー",
            55.0,
        ),
    ]

    output = GetForecastMissesUseCase(repo).execute(
        period_days=30,
        track_type="芝",
        actual_label="ハイ",
        offset=1,
        limit=1,
        now=NOW,
    )

    assert output.date_from == "2026-06-24"
    assert output.date_to == "2026-07-23"
    assert output.total_count == 2
    assert output.offset == 1
    assert output.limit == 1
    assert [item.race_key for item in output.items] == ["2026071905010102"]
    assert all("rpci" not in vars(item) for item in output.items)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"track_type": "障害"}, "コース種別"),
        ({"predicted_label": "超ハイ"}, "展開区分"),
        ({"offset": -1}, "offset"),
        ({"limit": 101}, "limit"),
    ],
)
def test_rejects_invalid_miss_search_conditions(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        GetForecastMissesUseCase(FakeMartRepository()).execute(
            now=NOW,
            **kwargs,  # type: ignore[arg-type]
        )


def test_selected_period_does_not_shorten_weekly_trend() -> None:
    repo = FakeMartRepository()
    repo.prediction_evaluations = [
        _record(
            "2026071805010101",
            datetime.date(2026, 7, 18),
            "芝",
            "スロー",
            55.0,
        ),
        _record(
            "2026062005010102",
            datetime.date(2026, 6, 20),
            "芝",
            "平均",
            45.0,
        ),
    ]

    output = GetForecastPerformanceUseCase(repo).execute(period_days=30, now=NOW)

    assert output.date_from == "2026-06-24"
    assert output.period_days == 30
    assert output.sample_size == 1
    assert output.previous_period.groups[0].sample_size == 1
    assert sum(point.sample_size for point in output.weekly_trend) == 2


def test_rejects_unsupported_period() -> None:
    with pytest.raises(ValueError, match="集計期間"):
        GetForecastPerformanceUseCase(FakeMartRepository()).execute(
            period_days=60,
            now=NOW,
        )
