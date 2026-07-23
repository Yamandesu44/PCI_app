"""保存済み事前予想と確定結果から、表示用の予想精度を集計する。"""

from __future__ import annotations

import datetime

from pci.application.dto import (
    ForecastPerformanceGroupOutput,
    ForecastPerformanceOutput,
    ForecastPerformanceTrendPointOutput,
)
from pci.domain.pace.mart_repository import (
    MartRepository,
    PredictionEvaluationRecord,
)
from pci.domain.pace.rpci_forecast import classify_pace

_PERIOD_DAYS = 90
_TREND_WEEKS = 8
_JRA_TIMEZONE = datetime.timezone(datetime.timedelta(hours=9), name="JST")
_GROUPS = (
    ("overall", "全体", None),
    ("turf", "芝", "芝"),
    ("dirt", "ダート", "ダート"),
)
_CONFIDENCE_GROUPS = (
    ("strong", "読みやすい", 0.7, None),
    ("normal", "標準", 0.5, 0.7),
    ("caution", "変動注意", None, 0.5),
)


class GetForecastPerformanceUseCase:
    """直近90日の展開ラベル的中率を、内部実数値なしで返す。"""

    def __init__(self, repo: MartRepository) -> None:
        self._repo = repo

    def execute(
        self, *, now: datetime.datetime | None = None
    ) -> ForecastPerformanceOutput:
        current = now or datetime.datetime.now(datetime.UTC)
        date_to = current.astimezone(_JRA_TIMEZONE).date()
        date_from = date_to - datetime.timedelta(days=_PERIOD_DAYS - 1)
        records = self._repo.find_prediction_evaluations(date_from, date_to)
        groups = [
            _summarize(records, key=key, label=label, track_type=track_type)
            for key, label, track_type in _GROUPS
        ]
        confidence_groups = [
            _summarize_confidence(
                records,
                key=key,
                label=label,
                minimum=minimum,
                maximum=maximum,
            )
            for key, label, minimum, maximum in _CONFIDENCE_GROUPS
        ]
        weekly_trend = _build_weekly_trend(records, date_to)
        overall = groups[0]
        return ForecastPerformanceOutput(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            period_days=_PERIOD_DAYS,
            sample_size=overall.sample_size,
            hit_count=overall.hit_count,
            hit_rate=overall.hit_rate,
            groups=groups,
            confidence_groups=confidence_groups,
            weekly_trend=weekly_trend,
        )


def _summarize(
    records: list[PredictionEvaluationRecord],
    *,
    key: str,
    label: str,
    track_type: str | None,
) -> ForecastPerformanceGroupOutput:
    targets = [
        record
        for record in records
        if track_type is None or record.track_type == track_type
    ]
    hit_count = sum(
        str(classify_pace(record.actual_rpci, record.track_type))
        == record.predicted_label
        for record in targets
    )
    sample_size = len(targets)
    return ForecastPerformanceGroupOutput(
        key=key,
        label=label,
        sample_size=sample_size,
        hit_count=hit_count,
        hit_rate=round(hit_count / sample_size, 3) if sample_size else None,
    )


def _build_weekly_trend(
    records: list[PredictionEvaluationRecord],
    date_to: datetime.date,
) -> list[ForecastPerformanceTrendPointOutput]:
    """進行中の週を除き、直近8完了週を月曜始まりで集計する。"""
    last_sunday = date_to - datetime.timedelta(days=date_to.weekday() + 1)
    first_monday = last_sunday - datetime.timedelta(days=(_TREND_WEEKS * 7) - 1)
    points: list[ForecastPerformanceTrendPointOutput] = []
    for week_index in range(_TREND_WEEKS):
        week_from = first_monday + datetime.timedelta(days=week_index * 7)
        week_to = week_from + datetime.timedelta(days=6)
        targets = [
            record
            for record in records
            if week_from <= record.race_date <= week_to
        ]
        hit_count = sum(
            str(classify_pace(record.actual_rpci, record.track_type))
            == record.predicted_label
            for record in targets
        )
        sample_size = len(targets)
        points.append(
            ForecastPerformanceTrendPointOutput(
                date_from=week_from.isoformat(),
                date_to=week_to.isoformat(),
                sample_size=sample_size,
                hit_count=hit_count,
                hit_rate=(
                    round(hit_count / sample_size, 3)
                    if sample_size
                    else None
                ),
            )
        )
    return points


def _summarize_confidence(
    records: list[PredictionEvaluationRecord],
    *,
    key: str,
    label: str,
    minimum: float | None,
    maximum: float | None,
) -> ForecastPerformanceGroupOutput:
    targets = [
        record
        for record in records
        if (minimum is None or record.confidence >= minimum)
        and (maximum is None or record.confidence < maximum)
    ]
    hit_count = sum(
        str(classify_pace(record.actual_rpci, record.track_type))
        == record.predicted_label
        for record in targets
    )
    sample_size = len(targets)
    return ForecastPerformanceGroupOutput(
        key=key,
        label=label,
        sample_size=sample_size,
        hit_count=hit_count,
        hit_rate=round(hit_count / sample_size, 3) if sample_size else None,
    )
