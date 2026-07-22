"""SqlAlchemyRaceRepository 統合テスト。

testcontainers-postgres + Alembic マイグレーション済み DB を使用。
各テストはトランザクション ロールバックで隔離される。
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm import Session

from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import HorseModel, JockeyModel, TrainerModel
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository

pytestmark = pytest.mark.integration

RACE_KEY = RaceKey("2026061805010101")
RACE_DATE = datetime.date(2026, 6, 18)


def _make_race(status: RaceStatus = RaceStatus.ENTRIES) -> Race:
    return Race(
        race_key=RACE_KEY,
        race_date=RACE_DATE,
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=16,
        status=status,
    )


def _seed_master(session: Session) -> None:
    """horses / jockeys / trainers の最低限のマスタデータを投入。"""
    session.add(HorseModel(ketto_num="2020100001", name="テストホース", sex="牡", birth_year=2020))
    session.add(JockeyModel(code="01001", name="テスト騎手"))
    session.add(TrainerModel(code="01001", name="テスト調教師"))
    session.flush()


@pytest.mark.integration
class TestSaveAndFindRace:
    def test_save_and_find_by_key(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        race = _make_race()

        repo.save_race(race)
        db_session.flush()

        found = repo.find_by_key(RACE_KEY)
        assert found is not None
        assert found.race_key == RACE_KEY
        assert found.distance_m == 1600
        assert found.status == RaceStatus.ENTRIES

    def test_find_returns_none_for_unknown_key(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        result = repo.find_by_key(RaceKey("9999999999999999"))
        assert result is None

    def test_save_race_updates_status(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        race = _make_race()
        repo.save_race(race)
        db_session.flush()

        updated = Race(
            race_key=RACE_KEY,
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=16,
            status=RaceStatus.RESULT,
            rpci_actual=51.2,
            pci3_actual=52.0,
        )
        repo.save_race(updated)
        db_session.flush()

        found = repo.find_by_key(RACE_KEY)
        assert found is not None
        assert found.status == RaceStatus.RESULT
        assert found.rpci_actual == pytest.approx(51.2)


@pytest.mark.integration
class TestSaveAndFindEntries:
    def test_save_and_find_entries(self, db_session: Session) -> None:
        _seed_master(db_session)
        repo = SqlAlchemyRaceRepository(db_session)
        repo.save_race(_make_race())
        db_session.flush()

        entry = RaceEntry(
            race_key=RACE_KEY,
            horse_no=1,
            frame_no=1,
            ketto_num="2020100001",
            weight=480.0,
            jockey_code="01001",
            trainer_code="01001",
        )
        repo.save_entry(entry)
        db_session.flush()

        entries = repo.find_entries(RACE_KEY)
        assert len(entries) == 1
        assert entries[0].horse_no == 1
        assert entries[0].ketto_num == "2020100001"

    def test_entries_ordered_by_horse_no(self, db_session: Session) -> None:
        _seed_master(db_session)
        repo = SqlAlchemyRaceRepository(db_session)
        repo.save_race(_make_race())
        db_session.flush()

        for no in [3, 1, 2]:
            repo.save_entry(
                RaceEntry(
                    race_key=RACE_KEY,
                    horse_no=no,
                    frame_no=no,
                    ketto_num="2020100001",
                    weight=480.0,
                    jockey_code="01001",
                    trainer_code="01001",
                )
            )
        db_session.flush()

        horse_nos = [e.horse_no for e in repo.find_entries(RACE_KEY)]
        assert horse_nos == [1, 2, 3]


@pytest.mark.integration
class TestEnsureMastersSelfHeal:
    """実データ取り込み再現: マスタ未取得でも FK 違反で落ちないこと（本番 PG）。"""

    def test_register_entries_without_masters_succeeds(self, db_session: Session) -> None:
        from pci.application.dto import EntryInput, RaceInfo
        from pci.application.race_use_cases import RegisterRaceEntriesUseCase

        repo = SqlAlchemyRaceRepository(db_session)
        race_info = RaceInfo(
            race_key=str(RACE_KEY),
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=2,
        )
        entries = [
            EntryInput(
                horse_no=1, frame_no=1, ketto_num="2021000001",
                weight=470.0, jockey_code="05339", trainer_code="01088",
            ),
            EntryInput(
                horse_no=2, frame_no=2, ketto_num="2021000002",
                weight=482.0, jockey_code="05339", trainer_code="01099",
            ),
        ]
        # マスタを一切投入していない状態でも FK 違反 (IntegrityError) で落ちない
        RegisterRaceEntriesUseCase(repo).execute(race_info, entries)
        db_session.flush()

        found = repo.find_entries(RACE_KEY)
        assert len(found) == 2
        # 参照される馬/騎手/調教師がプレースホルダとして補完されている
        assert db_session.get(HorseModel, "2021000001") is not None
        assert db_session.get(JockeyModel, "05339") is not None
        assert db_session.get(TrainerModel, "01088") is not None
        assert db_session.get(TrainerModel, "01099") is not None

    def test_ensure_does_not_clobber_existing_master(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        db_session.add(JockeyModel(code="05339", name="本物騎手"))
        db_session.flush()

        repo.ensure_jockeys(["05339", "09999"])
        db_session.flush()

        existing = db_session.get(JockeyModel, "05339")
        placeholder = db_session.get(JockeyModel, "09999")
        assert existing is not None and existing.name == "本物騎手"  # 上書きしない
        assert placeholder is not None and placeholder.name == "09999"  # 欠損は補完


@pytest.mark.integration
class TestListRecentRaces:
    def _save_race(self, repo: SqlAlchemyRaceRepository, key_str: str, day: int) -> None:
        repo.save_race(
            Race(
                race_key=RaceKey(key_str),
                race_date=datetime.date(2026, 6, day),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
            )
        )

    def test_empty_db_returns_empty_list(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        assert repo.list_recent_races() == []

    def test_ordered_newest_first(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        self._save_race(repo, "2026061705010101", day=17)
        self._save_race(repo, "2026062005010101", day=20)
        self._save_race(repo, "2026061805010101", day=18)
        db_session.flush()

        dates = [r.race_date for r in repo.list_recent_races()]
        assert dates == [
            datetime.date(2026, 6, 20),
            datetime.date(2026, 6, 18),
            datetime.date(2026, 6, 17),
        ]

    def test_respects_limit(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        for day in range(1, 8):
            self._save_race(repo, f"202606{day:02d}05010101", day=day)
        db_session.flush()

        assert len(repo.list_recent_races(limit=3)) == 3


@pytest.mark.integration
class TestFindIncompletePastRaces:
    def test_counts_and_lists_only_past_entries(self, db_session: Session) -> None:
        repo = SqlAlchemyRaceRepository(db_session)
        for key, race_date, status in [
            ("2026061705010101", datetime.date(2026, 6, 17), RaceStatus.ENTRIES),
            ("2026061805010101", datetime.date(2026, 6, 18), RaceStatus.ENTRIES),
            ("2026061805010102", datetime.date(2026, 6, 18), RaceStatus.RESULT),
            ("2026061905010101", datetime.date(2026, 6, 19), RaceStatus.ENTRIES),
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
        db_session.flush()

        before = datetime.date(2026, 6, 19)
        assert repo.count_incomplete_past_races(before) == 2
        assert repo.find_oldest_incomplete_past_race_date(before) == datetime.date(2026, 6, 17)
        assert [str(race.race_key) for race in repo.find_incomplete_past_races(before)] == [
            "2026061805010101",
            "2026061705010101",
        ]


@pytest.mark.integration
class TestFindHorseRecentEntries:
    def test_returns_only_result_races(self, db_session: Session) -> None:
        _seed_master(db_session)
        repo = SqlAlchemyRaceRepository(db_session)

        # entries レース（取得されない）
        entries_race = Race(
            race_key=RaceKey("2026061805010102"),
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=1800,
            track_type="芝",
            field_size=10,
            status=RaceStatus.ENTRIES,
        )
        # result レース（取得される）
        result_race = Race(
            race_key=RaceKey("2026061705010101"),
            race_date=datetime.date(2026, 6, 17),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=12,
            status=RaceStatus.RESULT,
        )

        for r in [entries_race, result_race]:
            repo.save_race(r)
        db_session.flush()

        for race_key in [RaceKey("2026061805010102"), RaceKey("2026061705010101")]:
            repo.save_entry(
                RaceEntry(
                    race_key=race_key,
                    horse_no=1,
                    frame_no=1,
                    ketto_num="2020100001",
                    weight=480.0,
                    jockey_code="01001",
                    trainer_code="01001",
                    finish_pos=2,
                    race_time_s=94.4,
                    agari_3f_s=33.9,
                    corner_4=3,
                )
            )
        db_session.flush()

        recent = repo.find_horse_recent_entries("2020100001", limit=5)
        assert len(recent) == 1
        assert recent[0].race_key == RaceKey("2026061705010101")

    def test_respects_limit(self, db_session: Session) -> None:
        _seed_master(db_session)
        repo = SqlAlchemyRaceRepository(db_session)

        for i in range(7):
            date = datetime.date(2026, 1, i + 1)
            key_str = f"202601{i + 1:02d}05010101"
            race = Race(
                race_key=RaceKey(key_str),
                race_date=date,
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
            )
            repo.save_race(race)
            repo.save_entry(
                RaceEntry(
                    race_key=RaceKey(key_str),
                    horse_no=1,
                    frame_no=1,
                    ketto_num="2020100001",
                    weight=480.0,
                    jockey_code="01001",
                    trainer_code="01001",
                )
            )
        db_session.flush()

        recent = repo.find_horse_recent_entries("2020100001", limit=5)
        assert len(recent) == 5
