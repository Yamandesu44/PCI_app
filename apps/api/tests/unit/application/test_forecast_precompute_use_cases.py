"""予想事前生成ユースケースの単体テスト。"""

from __future__ import annotations

import datetime
from unittest.mock import Mock

from pci.application.forecast_precompute_use_cases import PrecomputeUpcomingForecastsUseCase
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_repository import FakeRaceRepository


def _save_race(
    repo: FakeRaceRepository,
    race_key: str,
    race_date: datetime.date,
    *,
    status: RaceStatus = RaceStatus.ENTRIES,
    with_entry: bool = True,
) -> None:
    repo.save_race(
        Race(
            race_key=RaceKey(race_key),
            race_date=race_date,
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=1,
            status=status,
        )
    )
    if with_entry:
        repo.save_entry(
            RaceEntry(
                race_key=RaceKey(race_key),
                horse_no=1,
                frame_no=1,
                ketto_num="2020100001",
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
            )
        )


def test_generates_only_upcoming_entry_races_with_entries() -> None:
    repo = FakeRaceRepository()
    today = datetime.date(2026, 7, 22)
    _save_race(repo, "2026072105010101", today - datetime.timedelta(days=1))
    _save_race(repo, "2026072205010101", today)
    _save_race(
        repo,
        "2026072205010102",
        today,
        status=RaceStatus.RESULT,
    )
    _save_race(repo, "2026072305010101", today + datetime.timedelta(days=1), with_entry=False)

    forecast = Mock(spec=ForecastRaceUseCase)
    output = PrecomputeUpcomingForecastsUseCase(repo, forecast).execute(
        today - datetime.timedelta(days=1),
        today + datetime.timedelta(days=1),
        today=today,
    )

    assert output.scanned == 3
    assert output.generated == 1
    assert output.skipped == 2
    forecast.execute.assert_called_once_with("2026072205010101")


def test_returns_empty_when_range_is_entirely_in_past() -> None:
    repo = FakeRaceRepository()
    forecast = Mock(spec=ForecastRaceUseCase)

    output = PrecomputeUpcomingForecastsUseCase(repo, forecast).execute(
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 2),
        today=datetime.date(2026, 7, 22),
    )

    assert output.scanned == output.generated == output.skipped == 0
    forecast.execute.assert_not_called()


def test_rejects_reversed_range() -> None:
    repo = FakeRaceRepository()
    forecast = Mock(spec=ForecastRaceUseCase)

    try:
        PrecomputeUpcomingForecastsUseCase(repo, forecast).execute(
            datetime.date(2026, 7, 23),
            datetime.date(2026, 7, 22),
        )
    except ValueError as exc:
        assert "開始日" in str(exc)
    else:
        raise AssertionError("逆転した日付範囲が拒否されませんでした。")
