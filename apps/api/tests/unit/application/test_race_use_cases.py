"""RegisterRaceEntriesUseCase / RecordRaceResultUseCase 単体テスト。"""

from __future__ import annotations

import datetime

import pytest

from pci.application.dto import EntryInput, RaceInfo, ResultInput
from pci.application.race_use_cases import (
    RecordRaceResultUseCase,
    RegisterRaceEntriesUseCase,
    UpdateRaceMetadataUseCase,
)
from pci.domain.racing.master import Horse
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
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

    def test_final_entries_replace_special_registration_snapshot(self) -> None:
        repo = self._make_repo()
        special_entries = [
            EntryInput(
                horse_no=i,
                frame_no=0,
                ketto_num=f"202010{i:04d}",
                weight=0.0,
                jockey_code="TBD",
                trainer_code="TBD",
            )
            for i in range(1, 20)
        ]
        special_info = RaceInfo(**{**RACE_INFO.__dict__, "field_size": 19})
        RegisterRaceEntriesUseCase(repo).execute(special_info, special_entries)

        accepted = RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        assert accepted == 3
        race = repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None and race.field_size == 3
        actual = repo.find_entries(RaceKey(RACE_KEY))
        assert [entry.horse_no for entry in actual] == [1, 2, 3]
        assert [entry.frame_no for entry in actual] == [1, 2, 3]
        assert [entry.ketto_num for entry in actual] == [
            "2020100001",
            "2020100002",
            "2020100003",
        ]

    def test_special_registration_does_not_overwrite_final_entries(self) -> None:
        repo = self._make_repo()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        special = [
            EntryInput(
                horse_no=1,
                frame_no=0,
                ketto_num="2020999999",
                weight=0.0,
                jockey_code="TBD",
                trainer_code="TBD",
            )
        ]

        accepted = RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, special)

        assert accepted == 0
        actual = repo.find_entries(RaceKey(RACE_KEY))
        assert len(actual) == 3
        assert actual[0].ketto_num == "2020100001"

    def test_same_final_snapshot_preserves_recorded_result(self) -> None:
        repo = self._make_repo()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        race = repo.find_by_key(RaceKey(RACE_KEY))
        horse = repo.find_entries(RaceKey(RACE_KEY))[0]
        assert race is not None and race.status == RaceStatus.RESULT
        assert race.rpci_actual is not None
        assert horse.finish_pos == 1
        assert horse.pci_actual is not None


class TestUpdateRaceMetadataUseCase:
    def test_updates_only_metadata_and_preserves_result(self) -> None:
        repo = FakeRaceRepository()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)
        before = repo.find_by_key(RaceKey(RACE_KEY))
        assert before is not None

        updated = UpdateRaceMetadataUseCase(repo).execute(
            RACE_KEY,
            track_type="障害",
            track_condition="稍重",
            weather="小雨",
        )

        after = repo.find_by_key(RaceKey(RACE_KEY))
        assert updated is True
        assert after is not None
        assert after.track_type == "障害"
        assert after.track_condition == "稍重"
        assert after.weather == "小雨"
        assert after.status == RaceStatus.RESULT
        assert after.rpci_actual == before.rpci_actual
        assert after.pci3_actual == before.pci3_actual
        assert len(repo.find_entries(RaceKey(RACE_KEY))) == 3

    def test_legacy_key_is_matched_by_date_place_and_race_no(self) -> None:
        repo = FakeRaceRepository()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        source_key = "2026061805020301"

        updated = UpdateRaceMetadataUseCase(repo).execute(
            source_key,
            track_condition="重",
            weather="雨",
        )

        legacy = repo.find_by_key(RaceKey(RACE_KEY))
        assert updated is True
        assert legacy is not None
        assert legacy.track_condition == "重"
        assert legacy.weather == "雨"
        assert repo.find_by_key(RaceKey(source_key)) is None

    def test_exact_and_legacy_keys_receive_the_same_metadata(self) -> None:
        repo = FakeRaceRepository()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        source_key = "2026061805020301"
        repo.save_race(
            Race(
                race_key=RaceKey(source_key),
                race_date=RACE_DATE,
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=3,
            )
        )

        updated = UpdateRaceMetadataUseCase(repo).execute(
            source_key,
            track_condition="重",
            weather="雨",
        )

        assert updated is True
        for key in (RACE_KEY, source_key):
            race = repo.find_by_key(RaceKey(key))
            assert race is not None
            assert race.track_condition == "重"
            assert race.weather == "雨"
    def test_legacy_key_is_not_matched_when_identity_is_ambiguous(self) -> None:
        repo = FakeRaceRepository()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)
        duplicate = Race(
            race_key=RaceKey("2026061805999901"),
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=3,
        )
        repo.save_race(duplicate)

        updated = UpdateRaceMetadataUseCase(repo).execute(
            "2026061805020301",
            track_condition="重",
        )

        assert updated is False
    def test_unknown_race_is_skipped(self) -> None:
        repo = FakeRaceRepository()

        updated = UpdateRaceMetadataUseCase(repo).execute(
            RACE_KEY,
            track_condition="良",
        )

        assert updated is False

    def test_empty_metadata_is_skipped(self) -> None:
        repo = FakeRaceRepository()
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, ENTRIES)

        updated = UpdateRaceMetadataUseCase(repo).execute(RACE_KEY)

        assert updated is False


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
        assert output.formula_version == "pci-v2"

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

    def test_rpci_from_lap_when_s3f_l3f_provided(self) -> None:
        """race_s3f / race_l3f が与えられたとき、ラップ由来 RPCI を採用する。

        S3=35s / L3=36s → calculate_rpci_from_lap → ≈47.2（前半がやや速い）。
        全馬 PCI 平均（イーブン≒50）とは値が異なることで、ラップ由来採用を確認する。
        """
        repo = self._setup_repo()
        output = RecordRaceResultUseCase(repo).execute(
            RACE_KEY, RESULTS, race_s3f=35.0, race_l3f=36.0
        )
        # S3/L3 由来: (35/36)*100-50 ≈ 47.2 がそのまま rpci になる
        assert output.rpci is not None
        assert output.rpci == pytest.approx(35.0 / 36.0 * 100 - 50, abs=0.15)

    def test_running_style_skipped_for_empty_ketto_num(self) -> None:
        """ketto_num="" の馬（出走表未登録）は脚質判定をスキップし None になる。"""
        repo = FakeRaceRepository()
        # 出走表を登録せずにレース情報だけ登録
        RegisterRaceEntriesUseCase(repo).execute(RACE_INFO, [])
        # horse_no=1 は出走表にないため ketto_num="" になる
        single_result = [
            ResultInput(horse_no=1, finish_pos=1, race_time_s=94.4, agari_3f_s=34.0)
        ]
        RecordRaceResultUseCase(repo).execute(RACE_KEY, single_result)
        entries = repo.find_entries(RaceKey(RACE_KEY))
        assert entries[0].running_style is None

    def test_running_style_derived_from_prior_history(self) -> None:
        """過去走の4角通過順位データがある馬は脚質が算出される。"""
        repo = self._setup_repo()
        # horse_no=1 (ketto_num="2020100001") に過去3走（corner_4=1 → ESCAPE）を追加
        for i in range(3):
            prev_key = f"202604{i + 1:02d}05010101"
            repo.save_race(
                Race(
                    race_key=RaceKey(prev_key),
                    race_date=datetime.date(2026, 4, i + 1),
                    jyo_cd="05",
                    distance_m=1600,
                    track_type="芝",
                    field_size=12,
                    status=RaceStatus.RESULT,
                )
            )
            repo.save_entry(
                RaceEntry(
                    race_key=RaceKey(prev_key),
                    horse_no=99,
                    frame_no=1,
                    ketto_num="2020100001",
                    weight=480.0,
                    jockey_code="J001",
                    trainer_code="T001",
                    finish_pos=2,
                    corner_4=1,
                )
            )

        RecordRaceResultUseCase(repo).execute(RACE_KEY, RESULTS)

        entries = repo.find_entries(RaceKey(RACE_KEY))
        horse1 = next(e for e in entries if e.horse_no == 1)
        assert horse1.running_style == "逃げ"  # corner_4=1 × 3走 → ESCAPE

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
