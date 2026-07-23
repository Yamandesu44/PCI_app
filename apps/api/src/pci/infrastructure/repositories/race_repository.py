"""RaceRepository の SQLAlchemy 実装。"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race, RaceStatus, TrackType
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import (
    DuplicateRaceAuditGroup,
    DuplicateRaceGroup,
    DuplicateRaceKeyAudit,
)
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import (
    HorseModel,
    JockeyModel,
    PaceFitModel,
    PredictedPaceModel,
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

    def list_recent_races(self, limit: int = 50) -> list[Race]:
        """新しい順にレース一覧を返す（トップ画面のレース選択用）。"""
        stmt = (
            select(RaceModel)
            .order_by(RaceModel.race_date.desc(), RaceModel.race_key.desc())
            .limit(limit)
        )
        return [self._to_race(m) for m in self._s.scalars(stmt).all()]

    def list_race_dates(self) -> list[datetime.date]:
        """全開催日を昇順で返す（カレンダー表示用）。"""
        stmt = select(func.distinct(RaceModel.race_date)).order_by(RaceModel.race_date)
        return list(self._s.scalars(stmt).all())

    def list_races_by_date(self, date: datetime.date) -> list[Race]:
        """指定日のレース一覧を返す。"""
        stmt = (
            select(RaceModel)
            .where(RaceModel.race_date == date)
            .order_by(RaceModel.race_key)
        )
        return [self._to_race(m) for m in self._s.scalars(stmt).all()]

    def count_incomplete_past_races(self, before: datetime.date) -> int:
        """指定日より前で、結果未反映のJRA平地レース件数を返す。"""
        stmt = select(func.count()).select_from(RaceModel).where(
            RaceModel.race_date < before,
            RaceModel.status == str(RaceStatus.ENTRIES),
            RaceModel.jyo_cd.in_(_JRA_PLACE_CODES),
            RaceModel.track_type != str(TrackType.HURDLE),
        )
        return int(self._s.scalar(stmt) or 0)

    def find_oldest_incomplete_past_race_date(
        self, before: datetime.date
    ) -> datetime.date | None:
        """再同期範囲の算出に使う、結果未反映レースの最古開催日を返す。"""
        stmt = select(func.min(RaceModel.race_date)).where(
            RaceModel.race_date < before,
            RaceModel.status == str(RaceStatus.ENTRIES),
            RaceModel.jyo_cd.in_(_JRA_PLACE_CODES),
            RaceModel.track_type != str(TrackType.HURDLE),
        )
        return self._s.scalar(stmt)

    def find_incomplete_past_races(
        self, before: datetime.date, limit: int = 20
    ) -> list[Race]:
        """指定日より前で、結果未反映のレースを新しい順に返す。"""
        stmt = (
            select(RaceModel)
            .where(
                RaceModel.race_date < before,
                RaceModel.status == str(RaceStatus.ENTRIES),
                RaceModel.jyo_cd.in_(_JRA_PLACE_CODES),
                RaceModel.track_type != str(TrackType.HURDLE),
            )
            .order_by(RaceModel.race_date.desc(), RaceModel.race_key.desc())
            .limit(limit)
        )
        return [self._to_race(m) for m in self._s.scalars(stmt).all()]

    def count_missing_track_conditions(
        self, on_or_after: datetime.date, before: datetime.date
    ) -> int:
        """指定期間内で馬場状態が未反映の確定済みJRA平地レース件数を返す。"""
        stmt = select(func.count()).select_from(RaceModel).where(
            RaceModel.race_date >= on_or_after,
            RaceModel.race_date < before,
            RaceModel.status == str(RaceStatus.RESULT),
            RaceModel.jyo_cd.in_(_JRA_PLACE_CODES),
            RaceModel.track_type != str(TrackType.HURDLE),
            RaceModel.track_condition.is_(None),
        )
        return int(self._s.scalar(stmt) or 0)

    def find_missing_track_conditions(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 20,
    ) -> list[Race]:
        """指定期間内で馬場状態が未反映の確定レースを新しい順に返す。"""
        stmt = (
            select(RaceModel)
            .where(
                RaceModel.race_date >= on_or_after,
                RaceModel.race_date < before,
                RaceModel.status == str(RaceStatus.RESULT),
                RaceModel.jyo_cd.in_(_JRA_PLACE_CODES),
                RaceModel.track_type != str(TrackType.HURDLE),
                RaceModel.track_condition.is_(None),
            )
            .order_by(RaceModel.race_date.desc(), RaceModel.race_key.desc())
            .limit(limit)
        )
        return [self._to_race(m) for m in self._s.scalars(stmt).all()]

    def count_duplicate_race_groups(
        self, on_or_after: datetime.date, before: datetime.date
    ) -> int:
        """指定期間内の、日付・競馬場・R番号が重複するJRA平地レース組数を返す。"""
        race_no: ColumnElement[Any] = literal_column("right(races.race_key, 2)")
        groups = (
            select(
                RaceModel.race_date,
                RaceModel.jyo_cd,
                race_no.label("race_no"),
            )
            .where(*self._duplicate_race_conditions(on_or_after, before))
            .group_by(RaceModel.race_date, RaceModel.jyo_cd, race_no)
            .having(func.count() > 1)
            .subquery()
        )
        return int(self._s.scalar(select(func.count()).select_from(groups)) or 0)

    def find_duplicate_race_groups(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 20,
    ) -> list[DuplicateRaceGroup]:
        """指定期間内の重複レース組を新しい順に返す。"""
        race_no: ColumnElement[Any] = literal_column("right(races.race_key, 2)")
        stmt = (
            select(
                RaceModel.race_date,
                RaceModel.jyo_cd,
                race_no.label("race_no"),
                func.array_agg(RaceModel.race_key).label("race_keys"),
            )
            .where(*self._duplicate_race_conditions(on_or_after, before))
            .group_by(RaceModel.race_date, RaceModel.jyo_cd, race_no)
            .having(func.count() > 1)
            .order_by(RaceModel.race_date.desc(), RaceModel.jyo_cd, race_no)
            .limit(limit)
        )
        return [
            DuplicateRaceGroup(
                race_date=row.race_date,
                jyo_cd=row.jyo_cd,
                race_no=row.race_no,
                race_keys=tuple(sorted(row.race_keys)),
            )
            for row in self._s.execute(stmt)
        ]

    def find_duplicate_race_audits(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 10_000,
    ) -> list[DuplicateRaceAuditGroup]:
        """重複キーごとの関連データ件数と内容ハッシュを返す。書き込みは行わない。"""
        groups = self.find_duplicate_race_groups(on_or_after, before, limit=limit)
        race_keys = [key for group in groups for key in group.race_keys]
        if not race_keys:
            return []

        races = {
            model.race_key: model
            for model in self._s.scalars(
                select(RaceModel).where(RaceModel.race_key.in_(race_keys))
            )
        }
        entries_by_key: dict[str, list[RaceEntryModel]] = {}
        for entry in self._s.scalars(
            select(RaceEntryModel)
            .where(RaceEntryModel.race_key.in_(race_keys))
            .order_by(RaceEntryModel.race_key, RaceEntryModel.horse_no)
        ):
            entries_by_key.setdefault(entry.race_key, []).append(entry)
        predicted_counts = self._count_by_race_key(PredictedPaceModel, race_keys)
        fit_counts = self._count_by_race_key(PaceFitModel, race_keys)

        return [
            DuplicateRaceAuditGroup(
                race_date=group.race_date,
                jyo_cd=group.jyo_cd,
                race_no=group.race_no,
                keys=tuple(
                    self._build_duplicate_key_audit(
                        races[key],
                        entries_by_key.get(key, []),
                        predicted_counts.get(key, 0),
                        fit_counts.get(key, 0),
                    )
                    for key in group.race_keys
                ),
            )
            for group in groups
        ]

    def _count_by_race_key(
        self, model: type[PredictedPaceModel] | type[PaceFitModel], race_keys: list[str]
    ) -> dict[str, int]:
        rows = self._s.execute(
            select(model.race_key, func.count())
            .where(model.race_key.in_(race_keys))
            .group_by(model.race_key)
        )
        return {race_key: int(count) for race_key, count in rows}

    @classmethod
    def _build_duplicate_key_audit(
        cls,
        race: RaceModel,
        entries: list[RaceEntryModel],
        predicted_pace_count: int,
        pace_fit_count: int,
    ) -> DuplicateRaceKeyAudit:
        finished = [entry for entry in entries if entry.finish_pos is not None]
        entry_values = [
            (entry.horse_no, entry.frame_no, entry.ketto_num)
            for entry in entries
        ]
        # 馬ID・人気・賞金は再取り込み時期で変わり得るため、
        # 馬番に対応する中核成績だけで実結果の衝突を判定する。
        result_values = [
            (
                entry.horse_no,
                entry.finish_pos,
                entry.race_time_s,
                entry.agari_3f_s,
                entry.corner_1,
                entry.corner_2,
                entry.corner_3,
                entry.corner_4,
            )
            for entry in finished
        ]
        return DuplicateRaceKeyAudit(
            race_key=race.race_key,
            status=race.status,
            field_size=race.field_size,
            entry_count=len(entries),
            finished_count=len(finished),
            entry_signature=cls._content_signature(entry_values),
            result_signature=cls._content_signature(result_values),
            predicted_pace_count=predicted_pace_count,
            pace_fit_count=pace_fit_count,
        )

    @staticmethod
    def _content_signature(values: list[tuple[Any, ...]]) -> str:
        payload = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("ascii")).hexdigest()

    @staticmethod
    def _duplicate_race_conditions(
        on_or_after: datetime.date, before: datetime.date
    ) -> tuple[Any, ...]:
        return (
            RaceModel.race_date >= on_or_after,
            RaceModel.race_date < before,
            RaceModel.jyo_cd.in_(_JRA_PLACE_CODES),
            RaceModel.track_type != str(TrackType.HURDLE),
            func.length(RaceModel.race_key) == 16,
        )

    def find_horse_recent_entries(
        self, ketto_num: str, limit: int = 5, before: datetime.date | None = None
    ) -> list[RaceEntry]:
        """馬の直近レース成績を確定レースから取得する（脚質判定・PAI算出の入力）。

        before 指定時はその日より前のレースだけを対象にする（バックテストの
        lookahead 防止）。日付フィルタを SQL 側で行うため limit が正しく効く。
        """
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
        if before is not None:
            stmt = stmt.where(RaceModel.race_date < before)
        return [self._to_entry(m) for m in self._s.scalars(stmt).all()]

    def find_horse_names(self, ketto_nums: Iterable[str]) -> dict[str, str]:
        wanted = list(ketto_nums)
        if not wanted:
            return {}
        rows = self._s.execute(
            select(HorseModel.ketto_num, HorseModel.name).where(
                HorseModel.ketto_num.in_(wanted)
            )
        ).all()
        return {r.ketto_num: r.name for r in rows}

    # ----- 書き込み -----

    def save_race(self, race: Race) -> None:
        self._s.merge(self._from_race(race))

    def save_entry(self, entry: RaceEntry) -> None:
        race_key = str(entry.race_key)
        existing = self._s.get(RaceEntryModel, (race_key, entry.horse_no))
        # 出走馬・馬番・枠の変更時だけ予想を破棄する。結果項目の更新では、
        # 出走前予想を確定後の答え合わせに残す。
        if (
            existing is None
            or existing.frame_no != entry.frame_no
            or existing.ketto_num != entry.ketto_num
        ):
            self._s.execute(delete(PaceFitModel).where(PaceFitModel.race_key == race_key))
            self._s.execute(
                delete(PredictedPaceModel).where(PredictedPaceModel.race_key == race_key)
            )
        self._s.merge(self._from_entry(entry))

    def delete_entries_not_in(self, key: RaceKey, horse_nos: set[int]) -> int:
        """完全な出馬表から消えた特別登録馬・旧馬番を削除する。"""
        race_key = str(key)
        stmt = delete(RaceEntryModel).where(RaceEntryModel.race_key == race_key)
        if horse_nos:
            stmt = stmt.where(RaceEntryModel.horse_no.not_in(horse_nos))
        cursor = cast(CursorResult[Any], self._s.execute(stmt))
        deleted = int(cursor.rowcount or 0)
        if deleted:
            self._s.execute(delete(PaceFitModel).where(PaceFitModel.race_key == race_key))
            self._s.execute(
                delete(PredictedPaceModel).where(PredictedPaceModel.race_key == race_key)
            )
        return deleted

    def delete_race(self, key: RaceKey) -> bool:
        """レース本体と、画面表示に関わる関連データをまとめて削除する。"""
        race_key = str(key)
        self._s.execute(delete(PaceFitModel).where(PaceFitModel.race_key == race_key))
        self._s.execute(delete(PredictedPaceModel).where(PredictedPaceModel.race_key == race_key))
        self._s.execute(delete(RaceEntryModel).where(RaceEntryModel.race_key == race_key))
        cursor = cast(
            CursorResult[Any],
            self._s.execute(delete(RaceModel).where(RaceModel.race_key == race_key)),
        )
        return bool(cursor.rowcount)

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
            popularity=m.popularity,
            prize_money=m.prize_money,
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

    # ----- FK 整合の自己修復 -----
    # 実データ取り込みでは、出走表(race_entries)が参照する馬/騎手/調教師マスタが
    # 未取得（DIFF セットアップ未実行など）だと FK 違反で INSERT が落ちる。
    # 出走表保存の前に欠損マスタをプレースホルダ（name=コード）で補完しておく。
    # 後で本物のマスタが届けば merge で名前が上書きされる（冪等・順不同で安全）。
    # flush() で entries より先にマスタを INSERT し、同一トランザクション内の
    # FK 解決順序を保証する。

    def ensure_horses(self, ketto_nums: Iterable[str]) -> None:
        wanted = {k for k in ketto_nums if k}
        if not wanted:
            return
        existing = set(
            self._s.scalars(
                select(HorseModel.ketto_num).where(HorseModel.ketto_num.in_(wanted))
            ).all()
        )
        for ketto in wanted - existing:
            self._s.add(HorseModel(ketto_num=ketto, name=ketto))
        self._s.flush()

    def ensure_jockeys(self, codes: Iterable[str]) -> None:
        wanted = {c for c in codes if c}
        if not wanted:
            return
        existing = set(
            self._s.scalars(
                select(JockeyModel.code).where(JockeyModel.code.in_(wanted))
            ).all()
        )
        for code in wanted - existing:
            self._s.add(JockeyModel(code=code, name=code))
        self._s.flush()

    def ensure_trainers(self, codes: Iterable[str]) -> None:
        wanted = {c for c in codes if c}
        if not wanted:
            return
        existing = set(
            self._s.scalars(
                select(TrainerModel.code).where(TrainerModel.code.in_(wanted))
            ).all()
        )
        for code in wanted - existing:
            self._s.add(TrainerModel(code=code, name=code))
        self._s.flush()

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
            popularity=e.popularity,
            prize_money=e.prize_money,
        )


_JRA_PLACE_CODES = tuple(f"{code:02d}" for code in range(1, 11))
