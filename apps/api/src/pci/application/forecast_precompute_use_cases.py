"""出走前レースの予想を事前生成するユースケース。"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.domain.racing.race import RaceStatus
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey


@dataclass(frozen=True)
class ForecastPrecomputeOutput:
    scanned: int
    generated: int
    skipped: int


class PrecomputeUpcomingForecastsUseCase:
    """指定期間にある今後の出走前レースの予想martを生成する。"""

    def __init__(
        self,
        repo: RaceRepository,
        forecast_use_case: ForecastRaceUseCase,
    ) -> None:
        self._repo = repo
        self._forecast_use_case = forecast_use_case

    def execute(
        self,
        date_from: datetime.date,
        date_to: datetime.date,
        *,
        today: datetime.date | None = None,
    ) -> ForecastPrecomputeOutput:
        if date_from > date_to:
            raise ValueError("開始日は終了日以前にしてください。")

        current_date = today or datetime.datetime.now(ZoneInfo("Asia/Tokyo")).date()
        current = max(date_from, current_date)
        if current > date_to:
            return ForecastPrecomputeOutput(scanned=0, generated=0, skipped=0)

        scanned = 0
        generated = 0
        skipped = 0
        while current <= date_to:
            for race in self._repo.list_races_by_date(current):
                scanned += 1
                if race.status != RaceStatus.ENTRIES:
                    skipped += 1
                    continue
                if not self._repo.find_entries(RaceKey(str(race.race_key))):
                    skipped += 1
                    continue
                self._forecast_use_case.execute(str(race.race_key))
                generated += 1
            current += datetime.timedelta(days=1)

        return ForecastPrecomputeOutput(
            scanned=scanned,
            generated=generated,
            skipped=skipped,
        )
