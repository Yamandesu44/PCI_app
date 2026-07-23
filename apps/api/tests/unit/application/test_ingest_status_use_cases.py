"""GetIngestStatusUseCase のテスト。"""

from __future__ import annotations

import datetime

from pci.application.ingest_status_use_cases import GetIngestStatusUseCase
from pci.domain.ops.ingest_log import IngestLogEntry
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_ingest_log_repository import FakeIngestLogRepository
from tests.unit.application.fake_repository import FakeRaceRepository

UTC = datetime.UTC
NOW = datetime.datetime(2026, 7, 22, 12, tzinfo=UTC)


def _entry(
    *,
    days_ago: int,
    status: str | None = "ok",
    step: str = "entries",
    error_msg: str | None = None,
) -> IngestLogEntry:
    started = NOW - datetime.timedelta(days=days_ago)
    return IngestLogEntry(
        batch_date=started.date(),
        step=step,
        mode="mykeibadb",
        started_at=started,
        finished_at=started + datetime.timedelta(minutes=5),
        status=status,
        error_msg=error_msg,
    )


class TestGetIngestStatusUseCase:
    @staticmethod
    def _execute(
        entries: list[IngestLogEntry], race_repo: FakeRaceRepository | None = None
    ):
        return GetIngestStatusUseCase(
            FakeIngestLogRepository(entries), race_repo or FakeRaceRepository()
        ).execute(now=NOW)

    def test_no_history_reports_not_applicable(self) -> None:
        output = self._execute([])
        assert output.has_history is False
        assert output.is_stale is False
        assert output.last_success_at is None
        assert output.recent_failures == []

    def test_recent_success_is_reported(self) -> None:
        entry = _entry(days_ago=1, step="results")
        output = self._execute([entry])
        assert output.has_history is True
        assert output.is_stale is False
        assert output.last_success_step == "results"
        assert output.last_success_at == entry.effective_time.isoformat()
        assert output.days_since_last_success == 1

    def test_stale_history_is_flagged(self) -> None:
        output = self._execute([_entry(days_ago=10)])
        assert output.is_stale is True

    def test_recent_failures_are_summarized_and_truncated(self) -> None:
        long_error = "x" * 500
        entries = [
            _entry(days_ago=0, status="error", step="entries", error_msg=long_error),
            _entry(days_ago=1, status="ok"),
        ]
        output = self._execute(entries)
        assert output.last_attempt_failed is True
        assert len(output.recent_failures) == 1
        failure = output.recent_failures[0]
        assert failure.step == "entries"
        assert failure.mode == "mykeibadb"
        assert len(failure.error_summary) == 200

    def test_recent_failures_capped_at_five(self) -> None:
        entries = [
            _entry(days_ago=i, status="error", error_msg=f"e{i}") for i in range(8)
        ]
        output = self._execute(entries)
        assert len(output.recent_failures) == 5

    def test_past_entries_are_reported_as_incomplete(self) -> None:
        repo = FakeRaceRepository()
        for key, race_date, status in [
            ("2026072005010101", datetime.date(2026, 7, 20), RaceStatus.ENTRIES),
            ("2026072105010102", datetime.date(2026, 7, 21), RaceStatus.ENTRIES),
            ("2026072105010103", datetime.date(2026, 7, 21), RaceStatus.RESULT),
            ("2026072205010104", datetime.date(2026, 7, 22), RaceStatus.ENTRIES),
        ]:
            repo.save_race(
                Race(
                    race_key=RaceKey(key),
                    race_date=race_date,
                    jyo_cd="05",
                    distance_m=1600,
                    track_type="芝",
                    field_size=12,
                    status=status,
                )
            )

        output = self._execute([_entry(days_ago=0)], repo)

        assert output.has_incomplete_races is True
        assert output.incomplete_race_count == 2
        assert [race.race_key for race in output.incomplete_races] == [
            "2026072105010102",
            "2026072005010101",
        ]

    def test_hurdle_and_non_jra_races_are_not_reported(self) -> None:
        repo = FakeRaceRepository()
        for key, jyo_cd, track_type in [
            ("2026072110010101", "10", "障害"),
            ("2026072142040109", "42", "ダート"),
            ("2026072105010102", "05", "芝"),
        ]:
            repo.save_race(
                Race(
                    race_key=RaceKey(key),
                    race_date=datetime.date(2026, 7, 21),
                    jyo_cd=jyo_cd,
                    distance_m=1600,
                    track_type=track_type,
                    field_size=12,
                    status=RaceStatus.ENTRIES,
                )
            )

        output = self._execute([_entry(days_ago=0)], repo)

        assert output.incomplete_race_count == 1
        assert [race.race_key for race in output.incomplete_races] == [
            "2026072105010102"
        ]

    def test_no_past_entries_reports_complete(self) -> None:
        output = self._execute([_entry(days_ago=0)])
        assert output.has_incomplete_races is False
        assert output.incomplete_race_count == 0
        assert output.recommended_sync_days_back == 10
        assert output.incomplete_races == []

    def test_sync_range_reaches_oldest_incomplete_race(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(
            Race(
                race_key=RaceKey("2026070105010101"),
                race_date=datetime.date(2026, 7, 1),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.ENTRIES,
            )
        )

        output = self._execute([_entry(days_ago=0)], repo)

        assert output.recommended_sync_days_back == 21

    def test_completeness_uses_jra_local_date(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(
            Race(
                race_key=RaceKey("2026072105010101"),
                race_date=datetime.date(2026, 7, 21),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.ENTRIES,
            )
        )
        utc_before_jst_midnight = datetime.datetime(2026, 7, 21, 14, 59, tzinfo=UTC)
        utc_after_jst_midnight = datetime.datetime(2026, 7, 21, 15, 1, tzinfo=UTC)
        use_case = GetIngestStatusUseCase(FakeIngestLogRepository([]), repo)

        assert use_case.execute(now=utc_before_jst_midnight).has_incomplete_races is False
        assert use_case.execute(now=utc_after_jst_midnight).has_incomplete_races is True

    def test_missing_track_conditions_are_reported_for_recent_results(self) -> None:
        repo = FakeRaceRepository()
        for key, race_date, status, track_type, track_condition in [
            (
                "2026072005010101",
                datetime.date(2026, 7, 20),
                RaceStatus.RESULT,
                "芝",
                None,
            ),
            (
                "2026071905010102",
                datetime.date(2026, 7, 19),
                RaceStatus.RESULT,
                "ダート",
                "良",
            ),
            (
                "2026071805010103",
                datetime.date(2026, 7, 18),
                RaceStatus.ENTRIES,
                "芝",
                None,
            ),
            (
                "2025072105010104",
                datetime.date(2025, 7, 21),
                RaceStatus.RESULT,
                "芝",
                None,
            ),
            (
                "2026071710010105",
                datetime.date(2026, 7, 17),
                RaceStatus.RESULT,
                "障害",
                None,
            ),
        ]:
            repo.save_race(
                Race(
                    race_key=RaceKey(key),
                    race_date=race_date,
                    jyo_cd=key[8:10],
                    distance_m=1600,
                    track_type=track_type,
                    field_size=12,
                    status=status,
                    track_condition=track_condition,
                )
            )

        output = self._execute([_entry(days_ago=0)], repo)

        assert output.race_metadata_date_from == "2025-07-22"
        assert output.race_metadata_date_to == "2026-07-22"
        assert output.has_missing_track_conditions is True
        assert output.missing_track_condition_count == 1
        assert [race.race_key for race in output.missing_track_condition_races] == [
            "2026072005010101"
        ]

    def test_no_missing_track_conditions_reports_complete(self) -> None:
        output = self._execute([_entry(days_ago=0)])

        assert output.has_missing_track_conditions is False
        assert output.missing_track_condition_count == 0
        assert output.missing_track_condition_races == []

    def test_duplicate_race_identities_are_reported(self) -> None:
        repo = FakeRaceRepository()
        for key, race_date, jyo_cd, track_type in [
            ("2026071902011211", datetime.date(2026, 7, 19), "10", "芝"),
            ("2026071910010111", datetime.date(2026, 7, 19), "10", "芝"),
            ("2026071903011209", datetime.date(2026, 7, 19), "03", "ダート"),
            ("2026071910030109", datetime.date(2026, 7, 19), "10", "障害"),
            ("2025071902011211", datetime.date(2025, 7, 19), "10", "芝"),
        ]:
            repo.save_race(
                Race(
                    race_key=RaceKey(key),
                    race_date=race_date,
                    jyo_cd=jyo_cd,
                    distance_m=1200,
                    track_type=track_type,
                    field_size=16,
                    status=RaceStatus.RESULT,
                )
            )

        output = self._execute([_entry(days_ago=0)], repo)

        assert output.has_duplicate_races is True
        assert output.duplicate_race_group_count == 1
        assert len(output.duplicate_race_groups) == 1
        group = output.duplicate_race_groups[0]
        assert group.race_date == "2026-07-19"
        assert group.jyo_cd == "10"
        assert group.race_no == "11"
        assert group.race_keys == [
            "2026071902011211",
            "2026071910010111",
        ]

    def test_no_duplicate_race_identities_reports_complete(self) -> None:
        output = self._execute([_entry(days_ago=0)])

        assert output.has_duplicate_races is False
        assert output.duplicate_race_group_count == 0
        assert output.duplicate_race_groups == []
