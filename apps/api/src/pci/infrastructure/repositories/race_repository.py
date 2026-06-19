"""RaceRepository の SQLAlchemy 実装。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import (
    HorseModel,
    JockeyModel,
    RaceEntryModel,
    RaceModel,
    TrainerModel,
)


class SqlAlchemyRaceRepository:
    """SQLAlchemy を使った RaceRepository 実装（ADR-0001: infra → domain 依存）。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    # ----- 読み取り -----

    def find_by_key(self, key: RaceKey) -> Race | None:
        model = self._s.get(RaceModel, str(key))
        return self._to_race(model) if model is not None else None

    def find_entries(self, key: RaceKey) -> list[RaceEntry]:
        stmt = (
            select(RaceEntryModel)
            .where(RaceEntryModel.race_key == str(key))
            .order_by(RaceEntryModel.horse_no)
        )
        return [self._to_entry(m) for m in self._s.scalars(stmt).all()]

    def find_horse_recent_entries(self, ketto_num: str, limit: int = 5) -> list[RaceEntry]:
        """馬の直近レース成績を確定レースから取得する（脚質判定・PAI算出の入力）。"""
        stmt = (
            select(RaceEntryModel)
            .join(RaceModel, RaceEntryModel.race_key == RaceModel.race_key)
            .where(
                RaceEntryModel.ketto_num == ketto_num,
                RaceModel.status == str(RaceStatus.RESULT),
            )
            .order_by(RaceModel.race_date.desc())
            .limit(limit)
        )
        return [self._to_entry(m) for m in self._s.scalars(stmt).all()]

    # ----- 書き込み -----

    def save_race(self, race: Race) -> None:
        self._s.merge(self._from_race(race))

    def save_entry(self, entry: RaceEntry) -> None:
        self._s.merge(self._from_entry(entry))

    # ----- 変換（domain ↔ ORM） -----

    def _to_race(self, m: RaceModel) -> Race:
        return Race(
            race_key=RaceKey(m.race_key),
            race_date=m.race_date,
            jyo_cd=m.jyo_cd,
            distance_m=m.distance_m,
            track_type=m.track_type,
            field_size=m.field_size,
            status=RaceStatus(m.status),
            track_condition=m.track_condition,
            weather=m.weather,
            grade=m.grade,
            race_class=m.race_class,
            rpci_actual=m.rpci_actual,
            pci3_actual=m.pci3_actual,
        )

    def _from_race(self, r: Race) -> RaceModel:
        return RaceModel(
            race_key=str(r.race_key),
            race_date=r.race_date,
            jyo_cd=r.jyo_cd,
            distance_m=r.distance_m,
            track_type=r.track_type,
            field_size=r.field_size,
            status=str(r.status),
            track_condition=r.track_condition,
            weather=r.weather,
            grade=r.grade,
            race_class=r.race_class,
            rpci_actual=r.rpci_actual,
            pci3_actual=r.pci3_actual,
        )

    def _to_entry(self, m: RaceEntryModel) -> RaceEntry:
        return RaceEntry(
            race_key=RaceKey(m.race_key),
            horse_no=m.horse_no,
            frame_no=m.frame_no,
            ketto_num=m.ketto_num,
            weight=m.weight,
            jockey_code=m.jockey_code,
            trainer_code=m.trainer_code,
            finish_pos=m.finish_pos,
            race_time_s=m.race_time_s,
            agari_3f_s=m.agari_3f_s,
            corner_1=m.corner_1,
            corner_2=m.corner_2,
            corner_3=m.corner_3,
            corner_4=m.corner_4,
            pci_actual=m.pci_actual,
            running_style=m.running_style,
        )

    def save_horse(self, horse: Horse) -> None:
        self._s.merge(HorseModel(
            ketto_num=horse.ketto_num,
            name=horse.name,
            sex=horse.sex,
            birth_year=horse.birth_year,
        ))

    def save_jockey(self, jockey: Jockey) -> None:
        self._s.merge(JockeyModel(code=jockey.code, name=jockey.name))

    def save_trainer(self, trainer: Trainer) -> None:
        self._s.merge(TrainerModel(code=trainer.code, name=trainer.name))

    def _from_entry(self, e: RaceEntry) -> RaceEntryModel:
        return RaceEntryModel(
            race_key=str(e.race_key),
            horse_no=e.horse_no,
            frame_no=e.frame_no,
            ketto_num=e.ketto_num,
            weight=e.weight,
            jockey_code=e.jockey_code,
            trainer_code=e.trainer_code,
            finish_pos=e.finish_pos,
            race_time_s=e.race_time_s,
            agari_3f_s=e.agari_3f_s,
            corner_1=e.corner_1,
            corner_2=e.corner_2,
            corner_3=e.corner_3,
            corner_4=e.corner_4,
            pci_actual=e.pci_actual,
            running_style=e.running_style,
        )
