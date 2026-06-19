"""SaveMasterDataUseCase 単体テスト。"""

from __future__ import annotations

from pci.application.ingest_use_cases import (
    HorseInput,
    JockeyInput,
    SaveMasterDataUseCase,
    TrainerInput,
)
from tests.unit.application.fake_repository import FakeRaceRepository


class TestSaveMasterDataUseCase:
    def _make(self) -> tuple[SaveMasterDataUseCase, FakeRaceRepository]:
        repo = FakeRaceRepository()
        return SaveMasterDataUseCase(repo), repo

    def test_save_horses_returns_count(self) -> None:
        uc, _ = self._make()
        inputs = [
            HorseInput(ketto_num="2020100001", name="テスト馬A"),
            HorseInput(ketto_num="2020100002", name="テスト馬B", sex="牡", birth_year=2020),
        ]
        assert uc.save_horses(inputs) == 2

    def test_save_horses_persists_to_repo(self) -> None:
        uc, repo = self._make()
        uc.save_horses([
            HorseInput(ketto_num="2020100001", name="テスト馬A", sex="牝", birth_year=2019),
        ])
        horse = repo._horses.get("2020100001")
        assert horse is not None
        assert horse.name == "テスト馬A"
        assert horse.sex == "牝"
        assert horse.birth_year == 2019

    def test_save_horses_optional_fields_none(self) -> None:
        uc, repo = self._make()
        uc.save_horses([HorseInput(ketto_num="2020100003", name="ノーデータ")])
        horse = repo._horses["2020100003"]
        assert horse.sex is None
        assert horse.birth_year is None

    def test_save_horses_empty_list_returns_zero(self) -> None:
        uc, _ = self._make()
        assert uc.save_horses([]) == 0

    def test_save_jockeys_returns_count(self) -> None:
        uc, _ = self._make()
        inputs = [JockeyInput(code="J001", name="武豊"), JockeyInput(code="J002", name="川田将雅")]
        assert uc.save_jockeys(inputs) == 2

    def test_save_jockeys_persists_to_repo(self) -> None:
        uc, repo = self._make()
        uc.save_jockeys([JockeyInput(code="J001", name="武豊")])
        jockey = repo._jockeys.get("J001")
        assert jockey is not None
        assert jockey.name == "武豊"

    def test_save_jockeys_empty_list_returns_zero(self) -> None:
        uc, _ = self._make()
        assert uc.save_jockeys([]) == 0

    def test_save_trainers_returns_count(self) -> None:
        uc, _ = self._make()
        inputs = [TrainerInput(code="T001", name="藤原英昭")]
        assert uc.save_trainers(inputs) == 1

    def test_save_trainers_persists_to_repo(self) -> None:
        uc, repo = self._make()
        uc.save_trainers([TrainerInput(code="T001", name="藤原英昭")])
        trainer = repo._trainers.get("T001")
        assert trainer is not None
        assert trainer.name == "藤原英昭"

    def test_save_trainers_empty_list_returns_zero(self) -> None:
        uc, _ = self._make()
        assert uc.save_trainers([]) == 0

    def test_upsert_overwrites_existing_horse(self) -> None:
        uc, repo = self._make()
        uc.save_horses([HorseInput(ketto_num="2020100001", name="旧名", sex="牡")])
        uc.save_horses([HorseInput(ketto_num="2020100001", name="新名", sex="牝")])
        assert repo._horses["2020100001"].name == "新名"
        assert repo._horses["2020100001"].sex == "牝"

    def test_multiple_saves_are_independent(self) -> None:
        uc, repo = self._make()
        uc.save_horses([HorseInput(ketto_num="2020100001", name="馬A")])
        uc.save_jockeys([JockeyInput(code="J001", name="騎手A")])
        uc.save_trainers([TrainerInput(code="T001", name="調教師A")])
        assert len(repo._horses) == 1
        assert len(repo._jockeys) == 1
        assert len(repo._trainers) == 1
