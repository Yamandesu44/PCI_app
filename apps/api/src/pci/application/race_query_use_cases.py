"""レース照会ユースケース（読み取り専用）。"""

from __future__ import annotations

from pci.application.dto import EntryDetailOutput, RaceDetailOutput
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey


class GetRaceDetailUseCase:
    """レースの基本情報・出走馬・確定指標を取得する。"""

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(self, race_key_str: str) -> RaceDetailOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")

        entries = self._repo.find_entries(key)
        return RaceDetailOutput(
            race_key=str(race.race_key),
            race_date=race.race_date.isoformat(),
            jyo_cd=race.jyo_cd,
            distance_m=race.distance_m,
            track_type=race.track_type,
            status=str(race.status),
            field_size=race.field_size,
            track_condition=race.track_condition,
            weather=race.weather,
            grade=race.grade,
            race_class=race.race_class,
            rpci_actual=race.rpci_actual,
            pci3_actual=race.pci3_actual,
            entries=[
                EntryDetailOutput(
                    horse_no=e.horse_no,
                    frame_no=e.frame_no,
                    ketto_num=e.ketto_num,
                    running_style=e.running_style,
                    pci_actual=e.pci_actual,
                    finish_pos=e.finish_pos,
                )
                for e in entries
            ],
        )
