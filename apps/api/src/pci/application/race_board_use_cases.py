"""レースボード用の一括照会ユースケース。"""

from __future__ import annotations

import datetime

from pci.application.dto import RaceBoardForecastOutput, RaceBoardItemOutput
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_query_use_cases import ListRacesUseCase
from pci.domain.pace.mart_repository import MartRepository, RaceBoardForecastRecord
from pci.domain.racing.race import RaceStatus
from pci.domain.racing.repository import RaceRepository


class ListRaceBoardUseCase:
    """指定日のレースと一覧用予想をまとめて返す。"""

    def __init__(
        self,
        repo: RaceRepository,
        mart_repo: MartRepository,
        forecast_use_case: ForecastRaceUseCase,
    ) -> None:
        self._repo = repo
        self._mart_repo = mart_repo
        self._forecast_use_case = forecast_use_case

    def execute(self, date: datetime.date) -> list[RaceBoardItemOutput]:
        races = ListRacesUseCase(self._repo).execute(date=date)
        forecast_keys = [r.race_key for r in races if r.status == str(RaceStatus.ENTRIES)]
        cached = self._mart_repo.find_race_board_forecasts(forecast_keys)

        items: list[RaceBoardItemOutput] = []
        for race in races:
            if race.status != str(RaceStatus.ENTRIES):
                items.append(RaceBoardItemOutput(race=race))
                continue

            record = cached.get(race.race_key)
            if record is not None:
                items.append(RaceBoardItemOutput(race=race, forecast=_from_record(record)))
                continue

            try:
                forecast = self._forecast_use_case.execute(race.race_key)
            except ValueError:
                items.append(RaceBoardItemOutput(race=race))
                continue

            top = max(forecast.horses, key=lambda horse: horse.pai, default=None)
            preview = (
                RaceBoardForecastOutput(
                    pace_label=forecast.pace_label,
                    confidence=forecast.confidence,
                    top_horse_no=top.horse_no,
                    top_horse_name=top.horse_name,
                    top_fit_label=top.fit_label,
                    top_fit_strength=_fit_strength(top.pai),
                )
                if top is not None
                else None
            )
            items.append(RaceBoardItemOutput(race=race, forecast=preview))
        return items


def _from_record(record: RaceBoardForecastRecord) -> RaceBoardForecastOutput:
    return RaceBoardForecastOutput(
        pace_label=record.pace_label,
        confidence=record.confidence,
        top_horse_no=record.top_horse_no,
        top_horse_name=record.top_horse_name,
        top_fit_label=record.top_fit_label,
        top_fit_strength=_fit_strength(record.top_pai),
    )


def _fit_strength(pai: float) -> str:
    """内部適性指数を一覧向けのカテゴリへ丸める。"""
    if pai >= 80:
        return "strong"
    if pai >= 70:
        return "notable"
    return "normal"
