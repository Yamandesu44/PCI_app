"""保存済み事前予想と確定結果から、表示用の予想精度を集計する。"""

from __future__ import annotations

import datetime

from pci.application.dto import (
    ForecastMissOutput,
    ForecastPaceMatrixCellOutput,
    ForecastPaceMatrixRowOutput,
    ForecastPerformanceComparisonOutput,
    ForecastPerformanceGroupOutput,
    ForecastPerformanceOutput,
    ForecastPerformanceTrendPointOutput,
)
from pci.domain.pace.mart_repository import (
    MartRepository,
    PredictionEvaluationRecord,
)
from pci.domain.pace.rpci_forecast import classify_pace

_DEFAULT_PERIOD_DAYS = 90
_ALLOWED_PERIOD_DAYS = frozenset({30, 90, 180})
_TREND_WEEKS = 8
_RECENT_MISS_LIMIT = 5
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
_PACE_GROUPS = (
    ("high", "速い流れ", "ハイ"),
    ("average", "平均的な流れ", "平均"),
    ("slow", "落ち着いた流れ", "スロー"),
)


class GetForecastPerformanceUseCase:
    """指定期間の展開ラベル的中率を、内部実数値なしで返す。"""

    def __init__(self, repo: MartRepository) -> None:
        self._repo = repo

    def execute(
        self,
        *,
        period_days: int = _DEFAULT_PERIOD_DAYS,
        now: datetime.datetime | None = None,
    ) -> ForecastPerformanceOutput:
        if period_days not in _ALLOWED_PERIOD_DAYS:
            msg = f"集計期間は {sorted(_ALLOWED_PERIOD_DAYS)} 日から選択してください"
            raise ValueError(msg)

        current = now or datetime.datetime.now(datetime.UTC)
        date_to = current.astimezone(_JRA_TIMEZONE).date()
        date_from = date_to - datetime.timedelta(days=period_days - 1)
        previous_date_to = date_from - datetime.timedelta(days=1)
        previous_date_from = previous_date_to - datetime.timedelta(
            days=period_days - 1
        )
        trend_date_from = _weekly_trend_date_from(date_to)
        records = self._repo.find_prediction_evaluations(
            min(previous_date_from, trend_date_from),
            date_to,
        )
        period_records = [
            record for record in records if date_from <= record.race_date <= date_to
        ]
        previous_records = [
            record
            for record in records
            if previous_date_from <= record.race_date <= previous_date_to
        ]
        eligible_race_count = self._repo.count_prediction_evaluation_candidates(
            date_from,
            date_to,
        )
        groups = [
            _summarize(period_records, key=key, label=label, track_type=track_type)
            for key, label, track_type in _GROUPS
        ]
        previous_groups = [
            _summarize(
                previous_records,
                key=key,
                label=label,
                track_type=track_type,
            )
            for key, label, track_type in _GROUPS
        ]
        confidence_groups = [
            _summarize_confidence(
                period_records,
                key=key,
                label=label,
                minimum=minimum,
                maximum=maximum,
            )
            for key, label, minimum, maximum in _CONFIDENCE_GROUPS
        ]
        pace_matrix = _build_pace_matrix(period_records)
        weekly_trend = _build_weekly_trend(records, date_to)
        recent_misses = _build_recent_misses(period_records)
        overall = groups[0]
        return ForecastPerformanceOutput(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            period_days=period_days,
            eligible_race_count=eligible_race_count,
            sample_size=overall.sample_size,
            coverage_rate=(
                round(overall.sample_size / eligible_race_count, 3)
                if eligible_race_count
                else None
            ),
            hit_count=overall.hit_count,
            hit_rate=overall.hit_rate,
            groups=groups,
            previous_period=ForecastPerformanceComparisonOutput(
                date_from=previous_date_from.isoformat(),
                date_to=previous_date_to.isoformat(),
                groups=previous_groups,
            ),
            confidence_groups=confidence_groups,
            pace_matrix=pace_matrix,
            weekly_trend=weekly_trend,
            recent_misses=recent_misses,
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
    first_monday = _weekly_trend_date_from(date_to)
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


def _weekly_trend_date_from(date_to: datetime.date) -> datetime.date:
    """直近8完了週の先頭となる月曜日を返す。"""
    last_sunday = date_to - datetime.timedelta(days=date_to.weekday() + 1)
    return last_sunday - datetime.timedelta(days=(_TREND_WEEKS * 7) - 1)


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


def _build_pace_matrix(
    records: list[PredictionEvaluationRecord],
) -> list[ForecastPaceMatrixRowOutput]:
    """予想3区分ごとに、実績3区分への分布を集計する。"""
    rows: list[ForecastPaceMatrixRowOutput] = []
    for predicted_key, predicted_label, predicted_value in _PACE_GROUPS:
        targets = [
            record
            for record in records
            if record.predicted_label == predicted_value
        ]
        sample_size = len(targets)
        actual_labels = [
            str(classify_pace(record.actual_rpci, record.track_type))
            for record in targets
        ]
        cells = []
        for actual_key, actual_label, actual_value in _PACE_GROUPS:
            count = actual_labels.count(actual_value)
            cells.append(
                ForecastPaceMatrixCellOutput(
                    key=actual_key,
                    label=actual_label,
                    count=count,
                    rate=(
                        round(count / sample_size, 3)
                        if sample_size
                        else None
                    ),
                )
            )
        rows.append(
            ForecastPaceMatrixRowOutput(
                predicted_key=predicted_key,
                predicted_label=predicted_label,
                sample_size=sample_size,
                cells=cells,
            )
        )
    return rows


def _build_recent_misses(
    records: list[PredictionEvaluationRecord],
) -> list[ForecastMissOutput]:
    """直近の不一致レースを、内部RPCI値を除いた表示情報へ変換する。"""
    misses = [
        (record, str(classify_pace(record.actual_rpci, record.track_type)))
        for record in records
        if str(classify_pace(record.actual_rpci, record.track_type))
        != record.predicted_label
    ]
    misses.sort(
        key=lambda item: (item[0].race_date, item[0].race_key),
        reverse=True,
    )
    return [
        ForecastMissOutput(
            race_key=record.race_key,
            race_date=record.race_date.isoformat(),
            jyo_cd=record.jyo_cd,
            distance_m=record.distance_m,
            track_type=record.track_type,
            race_class=record.race_class,
            predicted_label=record.predicted_label,
            actual_label=actual_label,
        )
        for record, actual_label in misses[:_RECENT_MISS_LIMIT]
    ]
