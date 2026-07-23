"""取り込み状況（鮮度・失敗履歴）の参照ユースケース。"""

from __future__ import annotations

import datetime

from pci.application.dto import (
    IncompleteRaceOutput,
    IngestFailureOutput,
    IngestStatusOutput,
    MissingTrackConditionRaceOutput,
)
from pci.domain.ops.ingest_log import IngestLogRepository, evaluate_freshness
from pci.domain.racing.repository import RaceCompletenessRepository

_HISTORY_LOOKBACK = 20
_RECENT_FAILURES_LIMIT = 5
_ERROR_SUMMARY_MAX_LEN = 200
_INCOMPLETE_RACES_LIMIT = 20
_MISSING_TRACK_CONDITIONS_LIMIT = 20
_RACE_METADATA_LOOKBACK_DAYS = 365
_DEFAULT_SYNC_DAYS_BACK = 10
_JRA_TIMEZONE = datetime.timezone(datetime.timedelta(hours=9), name="JST")


class GetIngestStatusUseCase:
    """直近の取り込みログから、データの鮮度・失敗有無を判定する。"""

    def __init__(
        self,
        repo: IngestLogRepository,
        race_repo: RaceCompletenessRepository,
    ) -> None:
        self._repo = repo
        self._race_repo = race_repo

    def execute(self, *, now: datetime.datetime | None = None) -> IngestStatusOutput:
        entries = self._repo.find_recent(limit=_HISTORY_LOOKBACK)
        now = now or datetime.datetime.now(datetime.UTC)
        freshness = evaluate_freshness(entries, now)
        race_date_today = now.astimezone(_JRA_TIMEZONE).date()
        incomplete_count = self._race_repo.count_incomplete_past_races(race_date_today)
        oldest_incomplete_date = self._race_repo.find_oldest_incomplete_past_race_date(
            race_date_today
        )
        incomplete_races = self._race_repo.find_incomplete_past_races(
            race_date_today, limit=_INCOMPLETE_RACES_LIMIT
        )
        metadata_date_from = race_date_today - datetime.timedelta(
            days=_RACE_METADATA_LOOKBACK_DAYS
        )
        missing_track_condition_count = (
            self._race_repo.count_missing_track_conditions(
                metadata_date_from, race_date_today
            )
        )
        missing_track_condition_races = (
            self._race_repo.find_missing_track_conditions(
                metadata_date_from,
                race_date_today,
                limit=_MISSING_TRACK_CONDITIONS_LIMIT,
            )
        )
        recommended_sync_days_back = _DEFAULT_SYNC_DAYS_BACK
        if oldest_incomplete_date is not None:
            recommended_sync_days_back = max(
                _DEFAULT_SYNC_DAYS_BACK,
                (race_date_today - oldest_incomplete_date).days,
            )

        failures = [
            IngestFailureOutput(
                batch_date=e.batch_date.isoformat(),
                step=e.step,
                mode=e.mode,
                started_at=e.started_at.isoformat(),
                error_summary=(e.error_msg or "")[:_ERROR_SUMMARY_MAX_LEN],
            )
            for e in freshness.recent_failures[:_RECENT_FAILURES_LIMIT]
        ]

        return IngestStatusOutput(
            has_history=freshness.has_history,
            last_success_at=(
                freshness.last_success.effective_time.isoformat()
                if freshness.last_success
                else None
            ),
            last_success_step=freshness.last_success.step if freshness.last_success else None,
            last_attempt_failed=freshness.last_attempt_failed,
            days_since_last_success=freshness.days_since_last_success,
            is_stale=freshness.is_stale,
            recent_failures=failures,
            has_incomplete_races=incomplete_count > 0,
            incomplete_race_count=incomplete_count,
            recommended_sync_days_back=recommended_sync_days_back,
            incomplete_races=[
                IncompleteRaceOutput(
                    race_key=str(race.race_key),
                    race_date=race.race_date.isoformat(),
                    jyo_cd=race.jyo_cd,
                    track_type=race.track_type,
                    distance_m=race.distance_m,
                )
                for race in incomplete_races
            ],
            race_metadata_date_from=metadata_date_from.isoformat(),
            race_metadata_date_to=race_date_today.isoformat(),
            has_missing_track_conditions=missing_track_condition_count > 0,
            missing_track_condition_count=missing_track_condition_count,
            missing_track_condition_races=[
                MissingTrackConditionRaceOutput(
                    race_key=str(race.race_key),
                    race_date=race.race_date.isoformat(),
                    jyo_cd=race.jyo_cd,
                    track_type=race.track_type,
                    distance_m=race.distance_m,
                )
                for race in missing_track_condition_races
            ],
        )
