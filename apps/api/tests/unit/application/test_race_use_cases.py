"""RegisterRaceEntriesUseCase / RecordRaceResultUseCase 単体テスト。"""

from __future__ import annotations

import datetime

import pytest

from pci.application.dto import EntryInput, RaceInfo, ResultInput
from pci.application.race_use_cases import RecordRaceResultUseCase, RegisterRaceEntriesUseCase
from pci.domain.racing.master import Horse
from pci.domain.racing.race import RaceStatus
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_repository import FakeRaceRepository

RACE_KEY = "2026061805010101"
RACE_DATE = datetime.date(2026, 6, 18)

RACE_INFO = RaceInfo(
    race_key=RACE_KEY,
    race_date=RACE_DATE,
    jyo_cd="05",
    distance_m=1600,
    track_type="芝",
    field_size=3,
)

ENTRIES = [
    EntryInput(
        horse_no=1,
        frame_no=1,
        ketto_num="2020100001",
        weight=480.0,
        jockey_code="J001",
        trainer_code="T001",
    ),
    EntryInput(
        horse_no=2,
        frame_no=2,
        ketto_num="2020100002",
        weight=476.0,
        jockey_code="J002",
        trainer_code="T002",
    ),
    EntryInput(
        horse_no=3,
        frame_no=3,
        ketto_num="2020100003",
        weight=490.0,
        jockey_code="J003",
        trainer_code="T003",
    ),
]

# 1600m・ほぼイーブンペース
RESULTS = [
    ResultInput(horse_no=1, finish_pos=1, race_time_s=94.4, agari_3f_s=34.0, corner_4=2),
    ResultInput(horse_no=2, finish_pos=2, race_time_s=94.6, agari_3f_s=34.2, corner_4=1),
    ResultInput(horse_no=3, finish_pos=3, race_time_s=95.0, agari_3f_s=34.5, corner_4=4),
]


class TestRegisterRaceEntriesUseCase:
    def _make_repo(self) -> FakeRaceRepository:
        return FakeRaceRepository()

    def test_creates_race_with_entries_status(self) -> None:
        repo = self._make_repo()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        race = repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None
        assert race.status == RaceStatus.ENTRIES
        assert race.distance_m == 1600

    def test_saves_all_entries(self) -> None:
        repo = self._make_repo()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        entries = repo.find_entries(RaceKey(RACE_KEY))
        assert len(entries) == 3
        horse_nos = [e.horse_no for e in entries]
        assert horse_nos == [1, 2, 3]

    def test_entries_have_correct_ketto_num(self) -> None:
        repo = self._make_repo()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        entries = repo.find_entries(RaceKey(RACE_KEY))
        assert entries[0].ketto_num == "2020100001"
        assert entries[1].ketto_num == "2020100002"

    def test_missing_masters_are_self_healed(self) -> None:
        """マスタ未取得でも出走表登録が FK 違反で落ちず、欠損マスタが補完される。

        実データ取り込み再現: DIFF セットアップ未実行で馬/騎手/調教師マスタが
        空でも、出走表登録は成功し参照先がプレースホルダで作られること。
        """
        repo = self._make_repo()
        # マスタは一切登録していない状態で出走表を登録
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        entries = repo.find_entries(RaceKey(RACE_KEY))
        assert len(entries) == 3
        # 参照される馬/騎手/調教師がプレースホルダとして補完されている
        assert repo._horses.keys() == {"2020100001", "2020100002", "2020100003"}
        assert repo._jockeys.keys() == {"J001", "J002", "J003"}
        assert repo._trainers.keys() == {"T001", "T002", "T003"}

    def test_real_master_overwrites_placeholder(self) -> None:
        """先に補完したプレースホルダは、後から届く本物のマスタで上書きできる。"""
        repo = self._make_repo()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        assert repo._horses["2020100001"].name == "2020100001"  # プレースホルダ

        repo.save_horse(Horse(ketto_num="2020100001", name="テストホース", sex="牡"))
        assert repo._horses["2020100001"].name == "テストホース"

    def test_race_optional_fields_stored(self) -> None:
        repo = self._make_repo()
        info_with_opts = RaceInfo(
            race_key=RACE_KEY,
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=2000,
            track_type="ダート",
            field_size=10,
            track_condition="良",
            weather="晴",
            grade="G1",
            race_class="3歳以上",
        )
        RegisterRaceEntriesUseCase(repo).execute(info_with_opts, [])

        race = repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None
        assert race.track_condition == "良"
        assert race.grade == "G1"


class TestRecordRaceResultUseCase:
    def _setup_repo(self) -> FakeRaceRepository:
        repo = FakeRaceRepository()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        return repo

    def test_race_status_updated_to_result(self) -> None:
        repo = self._setup_repo()
        RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        race = repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None
        assert race.status == RaceStatus.RESULT

    def test_rpci_is_calculated(self) -> None:
        repo = self._setup_repo()
        output = RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        assert output.rpci > 0
        assert output.formula_version == "pci-v1"

    def test_pci3_is_average_of_top3(self) -> None:
        repo = self._setup_repo()
        output = RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        # 全3頭なので pci3 == rpci
        assert output.pci3 is not None
        assert output.pci3 == pytest.approx(output.rpci, abs=0.2)

    def test_entry_pci_values_stored(self) -> None:
        repo = self._setup_repo()
        output = RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        assert 1 in output.entry_pcis
        assert 2 in output.entry_pcis
        assert 3 in output.entry_pcis
        for pci in output.entry_pcis.values():
            assert 30.0 < pci < 70.0

    def test_race_not_found_raises(self) -> None:
        repo = FakeRaceRepository()
        with pytest.raises(ValueError, match="レースが見つかりません"):
            RecordRaceResultUseCase(repo).execute("9999999999999999", RESULTS)

    def test_race_rpci_saved_to_db(self) -> None:
        repo = self._setup_repo()
        output = RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        race = repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None
        assert race.rpci_actual == pytest.approx(output.rpci)
        assert race.pci3_actual == pytest.approx(output.pci3)

    def test_track_condition_and_weather_updated(self) -> None:
        repo = self._setup_repo()
        RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS, track_condition="良", weather="晴")

        race = repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None
        assert race.track_condition == "良"
        assert race.weather == "晴"

    def test_even_pace_pci_near_50(self) -> None:
        """均等ペース条件で PCI ≈ 50 になること（ドメインルール保証）。"""
        repo = FakeRaceRepository()
        # 2000m: front=7F, 前半84秒(12秒/F), 後半36秒(12秒/F) → ratio=1 → PCI=50
        even_info = RaceInfo(
            race_key=RACE_KEY,
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=2000,
            track_type="芝",
            field_size=1,
        )
        even_entry = [
            EntryInput(
                horse_no=1,
                frame_no=1,
                ketto_num="2020100001",
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
            )
        ]
        RegisterRaceEntriesUseCase(repo).execute(even_info, even_entry)
        even_results = [ResultInput(horse_no=1, finish_pos=1, race_time_s=120.0, agari_3f_s=36.0)]
        output = RecordRaceResultUseCase(repo).execute(RACE_KEY, even_results)

        assert output.rpci == pytest.approx(50.0, abs=0.5)
